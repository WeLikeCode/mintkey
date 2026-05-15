// Package server provides the gRPC server for the Vault Adapter.
//
// Source: design §8 gRPC service; vault.proto; T-1.0.4.
package server

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"strings"

	vaultv1 "github.com/mintkey/mintkey/internal/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/cache"
	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// VaultServer is the gRPC server. It holds the KEK, VaultService, and a
// reference to the shared DEK cache for metrics emission.
type VaultServer struct {
	kek      []byte
	dekCache *cache.DEKCache
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

// grpcVaultServer implements vaultv1.VaultAdapterServer by delegating to VaultService.
type grpcVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	svc *VaultService
}

// GetCredential translates the proto request to VaultService args and returns the result.
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

// ValidateServiceIdentity is not yet implemented.
func (g *grpcVaultServer) ValidateServiceIdentity(_ context.Context, _ *vaultv1.ValidateServiceIdentityRequest) (*vaultv1.ValidateServiceIdentityResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented")
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

	grpcSrv := grpc.NewServer()

	healthSvc := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcSrv, healthSvc)
	healthSvc.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)

	vaultv1.RegisterVaultAdapterServer(grpcSrv, &grpcVaultServer{svc: svc})

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
