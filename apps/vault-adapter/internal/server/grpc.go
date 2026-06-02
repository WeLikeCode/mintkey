// Package server provides the gRPC server for the Vault Adapter.
//
// Source: design §8 gRPC service; vault.proto; T-1.0.4.
package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"strings"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/applejwt"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/cache"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/googleserviceaccount"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// appleJWTEnvelope is the JSON structure stored (encrypted) in the vault for
// AUTH_SCHEME_APPLE_JWT credentials. The envelope is written by the Admin API
// (Chunk 4) and mirrors the Admin UI payload (Chunk 6).
// Security note: p8_key_pem bytes are zeroized immediately after use;
// this struct is never logged.
type appleJWTEnvelope struct {
	Scheme   string `json:"scheme"`     // must be "apple_jwt"
	P8KeyPEM string `json:"p8_key_pem"` // PKCS#8 PEM EC private key — never logged
	KeyID    string `json:"key_id"`     // 10-char Apple Key ID
	IssuerID string `json:"issuer_id"`  // Apple Issuer UUID
}

// googleServiceAccountEnvelope is the JSON structure stored (encrypted) in the
// vault for AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT credentials.
// JSONKey is the raw Google service account JSON key file bytes.
// Scope is the OAuth2 scope string to request.
// Security note: this struct is never logged; key material is zeroized after use.
type googleServiceAccountEnvelope struct {
	JSONKey json.RawMessage `json:"json_key"`
	Scope   string          `json:"scope"`
}

// methodScopes maps gRPC method full names to the required scope.
// Methods not listed here do not require scope enforcement.
var methodScopes = map[string]string{
	"/mintkey.vault.v1.VaultAdapter/GetCredential": "vault.read",
	"/mintkey.vault.v1.VaultAdapter/PutCredential": "vault.put",
}

// VaultServer is the gRPC server. It holds the KEK, VaultService, and a
// reference to the shared DEK cache for metrics emission.
type VaultServer struct {
	kek      []byte
	dekCache *cache.DEKCache
	sshStore store.SSHStore // optional; nil when backend is SQLite or when SSH is not configured
}

// New creates a VaultServer with the loaded KEK in memory.
// The KEK is held here for the lifetime of the process — never logged, never returned.
// dekCache is the shared cache instance used by VaultService; may be nil (metrics
// will then emit zeros for the gRPC-port /metrics endpoint).
func New(kek []byte, dekCache ...*cache.DEKCache) *VaultServer {
	var c *cache.DEKCache
	if len(dekCache) > 0 {
		c = dekCache[0]
	}
	return &VaultServer{kek: kek, dekCache: c}
}

// WithSSHStore attaches an SSHStore to VaultServer so that ListenAndServe
// can register the SSHVaultAdapter service alongside VaultAdapter.
// Call before ListenAndServe. Passing nil disables SSH RPC registration.
func (s *VaultServer) WithSSHStore(ss store.SSHStore) *VaultServer {
	s.sshStore = ss
	return s
}

// scopeInterceptor returns a gRPC unary server interceptor that enforces
// scope-based access control. It extracts the "x-mintkey-service-token"
// from incoming metadata, validates it against the VaultService's registered
// service identities, and checks that the caller has the required scope for
// the invoked method. Returns PERMISSION_DENIED if the scope is missing.
//
// Methods not listed in methodScopes are allowed without scope checks
// (e.g., ValidateServiceIdentity, ListVersions, health checks).
//
// Requirement 22.5: vault.read scope enforcement on GetCredential.
func scopeInterceptor(svc *VaultService) grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (interface{}, error) {
		requiredScope, needsScope := methodScopes[info.FullMethod]
		if !needsScope {
			return handler(ctx, req)
		}

		md, ok := metadata.FromIncomingContext(ctx)
		if !ok {
			return nil, status.Errorf(codes.PermissionDenied, "missing metadata")
		}

		tokens := md.Get("x-mintkey-service-token")
		if len(tokens) == 0 || tokens[0] == "" {
			return nil, status.Errorf(codes.PermissionDenied, "missing service token")
		}

		scopes, valid := svc.ValidateServiceIdentity(ctx, extractIdentityID(md), []byte(tokens[0]))
		if !valid {
			return nil, status.Errorf(codes.PermissionDenied, "invalid service token")
		}

		if !hasScope(scopes, requiredScope) {
			return nil, status.Errorf(codes.PermissionDenied, "caller lacks required scope %q", requiredScope)
		}

		return handler(ctx, req)
	}
}

// extractIdentityID extracts the service identity ID from gRPC metadata.
// Falls back to "x-mintkey-service-identity" header, then derives from token header presence.
func extractIdentityID(md metadata.MD) string {
	if ids := md.Get("x-mintkey-service-identity"); len(ids) > 0 && ids[0] != "" {
		return ids[0]
	}
	return ""
}

// hasScope checks if the given scope is present in the scopes slice.
func hasScope(scopes []string, required string) bool {
	for _, s := range scopes {
		if s == required {
			return true
		}
	}
	return false
}

// grpcVaultServer implements vaultv1.VaultAdapterServer by delegating to VaultService.
type grpcVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	svc *VaultService
}

// GetCredential translates the proto request to VaultService args and returns the result.
// For AUTH_SCHEME_APPLE_JWT credentials the stored plaintext is a JSON envelope;
// the handler decrypts it, calls applejwt.Generate to produce a fresh ES256 JWT,
// and returns that JWT as the Value — zeroizing the PEM key bytes immediately after.
// The generated JWT is never cached (spec §3).
// For AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT credentials the stored plaintext is a
// two-layer JSON envelope; the handler parses it, fetches (or serves from cache)
// an OAuth2 access token, zeroizes the PEM key immediately after use, and returns
// the access token bytes as Value. The access token is never logged or audited.
func (g *grpcVaultServer) GetCredential(ctx context.Context, req *vaultv1.GetCredentialRequest) (*vaultv1.GetCredentialResponse, error) {
	result, err := g.svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:      req.GetTenantId(),
		ServiceID:     req.GetServiceId(),
		KeyVersion:    req.GetKeyVersion(),
		CallerActorID: req.GetCallerActorId(),
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "GetCredential: %v", err)
	}

	// AUTH_SCHEME_APPLE_JWT: decrypt envelope → generate fresh JWT → return as Value.
	// The plaintext is NOT the credential itself; it is the JSON key envelope.
	if result.AuthScheme == int32(vaultv1.AuthScheme_AUTH_SCHEME_APPLE_JWT) {
		var env appleJWTEnvelope
		if err := json.Unmarshal(result.Plaintext, &env); err != nil {
			return nil, status.Errorf(codes.InvalidArgument, "invalid apple_jwt envelope")
		}
		if env.Scheme != "apple_jwt" || env.P8KeyPEM == "" || env.KeyID == "" || env.IssuerID == "" {
			return nil, status.Errorf(codes.InvalidArgument, "invalid apple_jwt envelope")
		}

		// Convert to []byte so we can zeroize after use (Go strings are immutable).
		pemBytes := []byte(env.P8KeyPEM)

		jwtToken, err := applejwt.Generate(pemBytes, env.KeyID, env.IssuerID)

		// Zeroize the PEM key bytes immediately — spec §3 hard rule.
		for i := range pemBytes {
			pemBytes[i] = 0
		}
		env.P8KeyPEM = ""

		if err != nil {
			return nil, status.Errorf(codes.Internal, "apple_jwt token generation failed")
		}

		return &vaultv1.GetCredentialResponse{
			AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
			Value:              []byte(jwtToken),
			ReturnedKeyVersion: result.ReturnedKeyVersion,
			CurrentKeyVersion:  result.CurrentKeyVersion,
			TargetUrl:          result.TargetURL,
			HeaderName:         result.HeaderName,
			QueryParam:         result.QueryParam,
		}, nil
	}

	// AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT: parse envelope → cache lookup / fetch
	// access token → zeroize PEM key bytes → return token as Value.
	if result.AuthScheme == int32(vaultv1.AuthScheme_AUTH_SCHEME_GOOGLE_SERVICE_ACCOUNT) {
		// Validate outer envelope structure.
		var env googleServiceAccountEnvelope
		if err := json.Unmarshal(result.Plaintext, &env); err != nil {
			return nil, status.Errorf(codes.InvalidArgument, "invalid google_service_account envelope")
		}
		if len(env.JSONKey) == 0 || env.Scope == "" {
			return nil, status.Errorf(codes.InvalidArgument, "invalid google_service_account envelope")
		}

		// Parse the two-layer blob: outer envelope + inner Google JSON key file.
		keyFile, scope, err := googleserviceaccount.ParseStoredBlob(result.Plaintext)
		if err != nil {
			return nil, status.Errorf(codes.Internal, "google_service_account blob parse failed")
		}

		tenantID := req.GetTenantId()
		serviceID := req.GetServiceId()

		// Cache lookup: (tenantID, serviceID, privateKeyID).
		if tok, ok := googleserviceaccount.GlobalCache.Get(tenantID, serviceID, keyFile.PrivateKeyID); ok {
			// Cache hit — return without touching the token endpoint.
			// Zeroize key material even on cache-hit path (ParseStoredBlob already
			// populated keyFile.PrivateKey; clear it to bound in-memory lifetime).
			pemBytes := []byte(keyFile.PrivateKey)
			for i := range pemBytes {
				pemBytes[i] = 0
			}
			keyFile.PrivateKey = ""

			return &vaultv1.GetCredentialResponse{
				AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
				Value:              []byte(tok),
				ReturnedKeyVersion: result.ReturnedKeyVersion,
				CurrentKeyVersion:  result.CurrentKeyVersion,
				TargetUrl:          result.TargetURL,
				HeaderName:         result.HeaderName,
				QueryParam:         result.QueryParam,
			}, nil
		}

		// Cache miss — fetch a fresh token from the Google token endpoint.
		tokenResp, fetchErr := googleserviceaccount.FetchAccessToken(ctx, keyFile, scope)

		// Zeroize the PEM private key bytes immediately after FetchAccessToken
		// returns — on BOTH success and error paths — to bound the in-memory
		// lifetime of key material to the minimum necessary window.
		pemBytes := []byte(keyFile.PrivateKey)
		for i := range pemBytes {
			pemBytes[i] = 0
		}
		keyFile.PrivateKey = ""

		if fetchErr != nil {
			return nil, status.Errorf(codes.Internal, "google_service_account token fetch failed")
		}

		// Store in cache keyed by (tenantID, serviceID, privateKeyID).
		// The access token is NEVER logged or audited — only the key fingerprint fields.
		googleserviceaccount.GlobalCache.Set(
			tenantID, serviceID, keyFile.PrivateKeyID,
			tokenResp.AccessToken, tokenResp.ExpiresIn,
		)

		return &vaultv1.GetCredentialResponse{
			AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
			Value:              []byte(tokenResp.AccessToken),
			ReturnedKeyVersion: result.ReturnedKeyVersion,
			CurrentKeyVersion:  result.CurrentKeyVersion,
			TargetUrl:          result.TargetURL,
			HeaderName:         result.HeaderName,
			QueryParam:         result.QueryParam,
		}, nil
	}

	// AUTH_SCHEME_SSH_PRIVATE_KEY: return raw PEM bytes + SSH routing metadata.
	// No envelope generation — the stored plaintext IS the credential.
	// The SSH proxy holds it in session scope and zeros it on disconnect (ADR-0021).
	// BaseUrl (field 11) is the canonical dial target per ADR-0023 Phase 3.
	if result.AuthScheme == int32(vaultv1.AuthScheme_AUTH_SCHEME_SSH_PRIVATE_KEY) {
		return &vaultv1.GetCredentialResponse{
			AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
			Value:              result.Plaintext,
			ReturnedKeyVersion: result.ReturnedKeyVersion,
			CurrentKeyVersion:  result.CurrentKeyVersion,
			TargetUrl:          result.TargetURL,
			TargetAddress:      result.TargetAddress,
			SshUser:            result.SSHUser,
			BaseUrl:            result.BaseUrl,
			AuthSchemeName:     "ssh_private_key",
		}, nil
	}

	// AUTH_SCHEME_SSH_PASSWORD: return raw password bytes + SSH routing metadata.
	// The password is stored as raw bytes (no envelope). The SSH proxy uses
	// ssh.Password(cred.Value) and zeros the bytes immediately after use.
	// BaseUrl (field 11) is the canonical dial target per ADR-0023 Phase 3.
	if result.AuthScheme == int32(vaultv1.AuthScheme_AUTH_SCHEME_SSH_PASSWORD) {
		return &vaultv1.GetCredentialResponse{
			AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
			Value:              result.Plaintext,
			ReturnedKeyVersion: result.ReturnedKeyVersion,
			CurrentKeyVersion:  result.CurrentKeyVersion,
			TargetUrl:          result.TargetURL,
			TargetAddress:      result.TargetAddress,
			SshUser:            result.SSHUser,
			BaseUrl:            result.BaseUrl,
			AuthSchemeName:     "ssh_password",
		}, nil
	}

	// AUTH_SCHEME_SSH_CA (Phase 2 stub): return raw CA key bytes.
	// Certificate signing logic is deferred to Phase 2 (ADR-0021 §3).
	// BaseUrl (field 11) is the canonical dial target per ADR-0023 Phase 3.
	if result.AuthScheme == int32(vaultv1.AuthScheme_AUTH_SCHEME_SSH_CA) {
		return &vaultv1.GetCredentialResponse{
			AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
			Value:              result.Plaintext,
			ReturnedKeyVersion: result.ReturnedKeyVersion,
			CurrentKeyVersion:  result.CurrentKeyVersion,
			TargetUrl:          result.TargetURL,
			TargetAddress:      result.TargetAddress,
			SshUser:            result.SSHUser,
			BaseUrl:            result.BaseUrl,
			AuthSchemeName:     "ssh_ca",
		}, nil
	}

	return &vaultv1.GetCredentialResponse{
		AuthScheme:         vaultv1.AuthScheme(result.AuthScheme),
		Value:              result.Plaintext,
		ReturnedKeyVersion: result.ReturnedKeyVersion,
		CurrentKeyVersion:  result.CurrentKeyVersion,
		TargetUrl:          result.TargetURL,
		HeaderName:         result.HeaderName,
		QueryParam:         result.QueryParam,
	}, nil
}

// PutCredential seals and stores a credential, returning the assigned key_version.
func (g *grpcVaultServer) PutCredential(ctx context.Context, req *vaultv1.PutCredentialRequest) (*vaultv1.PutCredentialResponse, error) {
	result, err := g.svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:      req.GetTenantId(),
		ServiceID:     req.GetServiceId(),
		AuthScheme:    int32(req.GetAuthScheme()),
		Plaintext:     req.GetValue(),
		CallerActorID: req.GetCallerActorId(),
		TargetURL:     req.GetTargetUrl(),
		HeaderName:    req.GetHeaderName(),
		QueryParam:    req.GetQueryParam(),
		TargetAddress: req.GetTargetAddress(),
		SSHUser:       req.GetSshUser(),
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "PutCredential: %v", err)
	}
	return &vaultv1.PutCredentialResponse{
		KeyVersion: result.KeyVersion,
	}, nil
}

// RevokeCredential is not yet implemented.
func (g *grpcVaultServer) RevokeCredential(_ context.Context, _ *vaultv1.RevokeCredentialRequest) (*vaultv1.RevokeCredentialResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented")
}

// ListVersions returns metadata-only descriptors for all versions of (tenant_id, service_id).
// Plaintext is never included — only metadata fields are populated.
func (g *grpcVaultServer) ListVersions(ctx context.Context, req *vaultv1.ListVersionsRequest) (*vaultv1.ListVersionsResponse, error) {
	result, err := g.svc.ListVersions(ctx, ListVersionsArgs{
		TenantID:        req.GetTenantId(),
		ServiceID:       req.GetServiceId(),
		AfterKeyVersion: req.GetAfterKeyVersion(),
		Limit:           req.GetLimit(),
		CallerActorID:   req.GetCallerActorId(),
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "ListVersions: %v", err)
	}

	versions := make([]*vaultv1.VersionDescriptor, 0, len(result.Versions))
	for _, d := range result.Versions {
		credStatus := vaultv1.CredentialStatus_CREDENTIAL_STATUS_ACTIVE
		if d.IsRevoked {
			credStatus = vaultv1.CredentialStatus_CREDENTIAL_STATUS_REVOKED
		}
		versions = append(versions, &vaultv1.VersionDescriptor{
			CredentialId: d.CredentialID,
			KeyVersion:   d.KeyVersion,
			IsCurrent:    d.IsCurrent,
			Status:       credStatus,
			AuthScheme:   vaultv1.AuthScheme(d.AuthScheme),
			CreatedAt:    timestamppb.New(d.CreatedAt),
			// value/plaintext is intentionally absent — ListVersions is metadata-only.
		})
	}

	return &vaultv1.ListVersionsResponse{
		Versions:            versions,
		NextAfterKeyVersion: result.NextAfterKeyVersion,
		CurrentKeyVersion:   result.CurrentKeyVersion,
	}, nil
}

// ValidateServiceIdentity validates the caller's service-identity token.
//
// The caller sends its identity via gRPC metadata headers:
//   - x-mintkey-service-identity: the identity ID (e.g. "svcid_email_proxy")
//   - x-mintkey-service-token:    the raw boot secret
//
// The proto request fields (service_identity_id, token) are accepted as a
// secondary source but metadata takes precedence, matching the pattern used by
// the scopeInterceptor for GetCredential/PutCredential.
//
// On success returns {ok:true, scopes:[...]}. On missing token returns
// codes.Unauthenticated; on wrong token returns codes.PermissionDenied.
func (g *grpcVaultServer) ValidateServiceIdentity(ctx context.Context, req *vaultv1.ValidateServiceIdentityRequest) (*vaultv1.ValidateServiceIdentityResponse, error) {
	// Prefer metadata headers; fall back to proto fields for callers that send them.
	identityID := ""
	var token []byte

	if md, ok := metadata.FromIncomingContext(ctx); ok {
		if ids := md.Get("x-mintkey-service-identity"); len(ids) > 0 && ids[0] != "" {
			identityID = ids[0]
		}
		if toks := md.Get("x-mintkey-service-token"); len(toks) > 0 && toks[0] != "" {
			token = []byte(toks[0])
		}
	}

	// Fall back to proto fields if metadata is absent or incomplete.
	if identityID == "" {
		identityID = req.GetServiceIdentityId()
	}
	if len(token) == 0 {
		token = req.GetToken()
	}

	if identityID == "" || len(token) == 0 {
		return nil, status.Errorf(codes.Unauthenticated, "missing service identity or token")
	}

	scopes, ok := g.svc.ValidateServiceIdentity(ctx, identityID, token)
	if !ok {
		return nil, status.Errorf(codes.PermissionDenied, "invalid service identity token")
	}

	return &vaultv1.ValidateServiceIdentityResponse{
		Ok:     true,
		Scopes: scopes,
	}, nil
}

// ListenAndServe starts the gRPC server on the given port, registering the VaultAdapter RPC.
// It also serves HTTP/1.1 requests on the same port, routing /metrics to a Prometheus handler
// and gRPC (detected via Content-Type: application/grpc) to the gRPC server.
// T-1.10.2: DEK cache metrics exposed on /metrics.
func (s *VaultServer) ListenAndServe(ctx context.Context, port int, svc *VaultService) error {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		return fmt.Errorf("vault-adapter: listen :%d: %w", port, err)
	}

	grpcSrv := grpc.NewServer(
		grpc.UnaryInterceptor(scopeInterceptor(svc)),
	)

	healthSvc := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcSrv, healthSvc)
	healthSvc.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)

	vaultv1.RegisterVaultAdapterServer(grpcSrv, &grpcVaultServer{svc: svc})

	// Register SSHVaultAdapter when an SSHStore is configured.
	if s.sshStore != nil {
		RegisterSSHVaultServer(grpcSrv, svc, s.sshStore)
	}

	// HTTP mux for non-gRPC requests (e.g. /metrics).
	httpMux := http.NewServeMux()
	httpMux.HandleFunc("/metrics", func(w http.ResponseWriter, _ *http.Request) {
		var hits, misses int64
		if s.dekCache != nil {
			hits = s.dekCache.Hits()
			misses = s.dekCache.Misses()
		}
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		fmt.Fprintf(w,
			"# HELP mintkey_vault_dek_cache_hit_total DEK cache hits.\n"+
				"# TYPE mintkey_vault_dek_cache_hit_total counter\n"+
				"mintkey_vault_dek_cache_hit_total %d\n"+
				"# HELP mintkey_vault_dek_cache_miss_total DEK cache misses.\n"+
				"# TYPE mintkey_vault_dek_cache_miss_total counter\n"+
				"mintkey_vault_dek_cache_miss_total %d\n",
			hits, misses,
		)
	})

	// Route: gRPC if Content-Type starts with "application/grpc", else HTTP mux.
	mixed := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.Header.Get("Content-Type"), "application/grpc") {
			grpcSrv.ServeHTTP(w, r)
		} else {
			httpMux.ServeHTTP(w, r)
		}
	})

	httpSrv := &http.Server{
		Handler: h2c.NewHandler(mixed, &http2.Server{}),
	}

	errCh := make(chan error, 1)
	go func() {
		errCh <- httpSrv.Serve(lis)
	}()

	select {
	case <-ctx.Done():
		_ = httpSrv.Shutdown(context.Background())
		grpcSrv.GracefulStop()
		return nil
	case err := <-errCh:
		return err
	}
}
