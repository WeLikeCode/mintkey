// Package server — gRPC handler tests for ListVersions.
//
// These tests exercise the full gRPC layer (grpcVaultServer) using an
// in-process bufconn transport, so they validate the translation from
// proto request → VaultService → proto response without a network socket.
//
// Source: WS-10; vault.proto; T-1.3.1.
package server

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"net"
	"reflect"
	"testing"

	"github.com/go-jose/go-jose/v4"
	josejwt "github.com/go-jose/go-jose/v4/jwt"
	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"pgregory.net/rapid"
)

const bufSize = 1024 * 1024

// newTestGRPCServer spins up a grpcVaultServer backed by an in-memory store
// and returns a connected stub plus a cleanup func.
func newTestGRPCServer(t *testing.T) (vaultv1.VaultAdapterClient, func()) {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}
	s, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}

	svc := NewVaultService(kek, s)

	lis := bufconn.Listen(bufSize)
	srv := grpc.NewServer()
	vaultv1.RegisterVaultAdapterServer(srv, &grpcVaultServer{svc: svc})

	go func() { _ = srv.Serve(lis) }()

	conn, err := grpc.NewClient(
		"passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}

	cleanup := func() {
		conn.Close()
		srv.Stop()
		_ = s.Close()
	}
	return vaultv1.NewVaultAdapterClient(conn), cleanup
}

// TestGRPCListVersions_TwoVersions puts 2 credentials via gRPC PutCredential,
// then calls ListVersions and verifies:
//   - 2 entries are returned
//   - ordering is ASC by key_version
//   - version 2 is flagged is_current
//   - no plaintext bytes appear in any VersionDescriptor field
func TestGRPCListVersions_TwoVersions(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_grpc_list"
	serviceID := "svc_grpc_list"
	secrets := [][]byte{[]byte("first-secret"), []byte("second-secret")}

	var putVersions []uint32
	for _, secret := range secrets {
		resp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
			TenantId:  tenantID,
			ServiceId: serviceID,
			AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
			Value:     secret,
		})
		if err != nil {
			t.Fatalf("PutCredential: %v", err)
		}
		putVersions = append(putVersions, resp.KeyVersion)
	}

	if putVersions[0] >= putVersions[1] {
		t.Errorf("expected key_version to increment; got %d then %d", putVersions[0], putVersions[1])
	}

	listResp, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
		TenantId:  tenantID,
		ServiceId: serviceID,
	})
	if err != nil {
		t.Fatalf("ListVersions: %v", err)
	}

	if len(listResp.Versions) != 2 {
		t.Fatalf("expected 2 versions, got %d", len(listResp.Versions))
	}

	// ASC ordering.
	if listResp.Versions[0].KeyVersion >= listResp.Versions[1].KeyVersion {
		t.Errorf("versions not in ASC order: %d, %d",
			listResp.Versions[0].KeyVersion, listResp.Versions[1].KeyVersion)
	}

	// Only the latest (version 2) should be current.
	for _, v := range listResp.Versions {
		wantCurrent := v.KeyVersion == putVersions[1]
		if v.IsCurrent != wantCurrent {
			t.Errorf("version %d: IsCurrent=%v, want %v", v.KeyVersion, v.IsCurrent, wantCurrent)
		}
	}

	// CurrentKeyVersion convenience field should equal the latest version.
	if listResp.CurrentKeyVersion != putVersions[1] {
		t.Errorf("CurrentKeyVersion=%d, want %d", listResp.CurrentKeyVersion, putVersions[1])
	}

	// PLAINTEXT-LEAK CHECK: VersionDescriptor carries no value field.
	// The proto VersionDescriptor message has no bytes/value field at all;
	// we verify the secrets do not appear anywhere in the response string form.
	respStr := listResp.String()
	for _, secret := range secrets {
		if contains(respStr, string(secret)) {
			t.Errorf("SECURITY: plaintext %q leaked in ListVersions response", secret)
		}
	}
}

// TestGRPCListVersions_Empty verifies an empty list is returned (not an error)
// when no credentials exist for the given (tenant_id, service_id).
func TestGRPCListVersions_Empty(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	listResp, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
		TenantId:  "tenant_no_creds",
		ServiceId: "svc_no_creds",
	})
	if err != nil {
		t.Fatalf("ListVersions on empty store: %v", err)
	}
	if len(listResp.Versions) != 0 {
		t.Errorf("expected 0 versions for empty store, got %d", len(listResp.Versions))
	}
}

// TestGRPCListVersions_MissingTenantID verifies a validation error is returned
// when tenant_id is omitted.
func TestGRPCListVersions_MissingTenantID(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	_, err := client.ListVersions(ctx, &vaultv1.ListVersionsRequest{
		ServiceId: "svc_01",
	})
	if err == nil {
		t.Fatal("expected error for missing tenant_id, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.Internal {
		t.Errorf("expected codes.Internal, got %v", st.Code())
	}
}

// TestGRPCListVersions_PutAndGetUnaffected verifies that implementing
// ListVersions does not regress PutCredential or GetCredential behaviour.
func TestGRPCListVersions_PutAndGetUnaffected(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	plaintext := []byte("regression-check-secret")

	putResp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_regress",
		ServiceId:  "svc_regress",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      plaintext,
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}
	if putResp.KeyVersion == 0 {
		t.Errorf("expected non-zero key_version from PutCredential")
	}

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_regress",
		ServiceId:  "svc_regress",
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}
	if string(getResp.Value) != string(plaintext) {
		t.Errorf("GetCredential returned %q, want %q", getResp.Value, plaintext)
	}
}

// TestGRPCPutGetHeaderName verifies that header_name and query_param are
// persisted by PutCredential and returned by GetCredential (UX-C6).
func TestGRPCPutGetHeaderName(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_hdr_test"
	serviceID := "svc_hdr_test"
	wantHeader := "X-Custom-Auth"
	wantQuery := ""

	putResp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
		Value:      []byte("supersecret"),
		HeaderName: wantHeader,
		QueryParam: wantQuery,
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}
	if putResp.KeyVersion == 0 {
		t.Fatalf("expected non-zero key_version, got 0")
	}

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0, // current
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}
	if getResp.HeaderName != wantHeader {
		t.Errorf("GetCredential: HeaderName=%q, want %q", getResp.HeaderName, wantHeader)
	}
	if getResp.QueryParam != wantQuery {
		t.Errorf("GetCredential: QueryParam=%q, want %q", getResp.QueryParam, wantQuery)
	}
	if string(getResp.Value) != "supersecret" {
		t.Errorf("GetCredential: Value=%q, want %q", getResp.Value, "supersecret")
	}
}

// TestGRPCPutGetQueryParam verifies query_param is persisted and returned (UX-C6).
func TestGRPCPutGetQueryParam(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_qp_test"
	serviceID := "svc_qp_test"
	wantQuery := "access_token"

	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_QUERY,
		Value:      []byte("mykey"),
		QueryParam: wantQuery,
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}
	if getResp.QueryParam != wantQuery {
		t.Errorf("GetCredential: QueryParam=%q, want %q", getResp.QueryParam, wantQuery)
	}
}

// TestGRPCGetCredential_NullHeaderName verifies that credentials stored
// before UX-C6 (NULL/empty header_name) return empty string, not an error.
func TestGRPCGetCredential_NullHeaderName(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_legacy"
	serviceID := "svc_legacy"

	// Store without header_name (simulates pre-UX-C6 record).
	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("legacytok"),
		// HeaderName and QueryParam intentionally omitted (zero-value "").
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential: unexpected error for legacy credential: %v", err)
	}
	// Empty string expected — not an error.
	if getResp.HeaderName != "" {
		t.Errorf("expected empty HeaderName for legacy credential, got %q", getResp.HeaderName)
	}
}

// -----------------------------------------------------------------------
// OAuth2 Password Grant credential round-trip (auth_scheme=8)
// -----------------------------------------------------------------------

// TestGRPCOAuth2PasswordGrant_RoundTrip verifies that a JSON-encoded
// OAuth2PasswordGrantCredential payload stored via PutCredential with
// auth_scheme=8 is returned byte-for-byte identical by GetCredential.
// Validates: Requirement 19.3.
func TestGRPCOAuth2PasswordGrant_RoundTrip(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_oauth2_test"
	serviceID := "svc_oauth2_test"

	// JSON-encoded OAuth2PasswordGrantCredential payload per design doc.
	payload := []byte(`{
  "token_url": "https://dashboard-api-ps-prod.azurewebsites.net/api/auth/login",
  "credential_fields": {
    "username": "admin",
    "password": "secret123"
  },
  "token_response_path": "$.token",
  "token_request_headers": {
    "Content-Type": "application/json"
  }
}`)

	putResp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT,
		Value:      payload,
	})
	if err != nil {
		t.Fatalf("PutCredential (auth_scheme=8): %v", err)
	}
	if putResp.KeyVersion == 0 {
		t.Fatal("expected non-zero key_version")
	}

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0, // current
	})
	if err != nil {
		t.Fatalf("GetCredential (auth_scheme=8): %v", err)
	}

	// Verify auth_scheme is preserved.
	if getResp.AuthScheme != vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT {
		t.Errorf("expected auth_scheme=%d, got %d",
			vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT, getResp.AuthScheme)
	}

	// Verify the JSON payload is returned byte-for-byte identical.
	if string(getResp.Value) != string(payload) {
		t.Errorf("payload round-trip mismatch:\n  stored: %s\n  got:    %s", payload, getResp.Value)
	}
}

// TestGRPCOAuth2PasswordGrant_MinimalPayload verifies that a minimal
// OAuth2PasswordGrantCredential (only required fields) round-trips correctly.
func TestGRPCOAuth2PasswordGrant_MinimalPayload(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	tenantID := "tenant_oauth2_min"
	serviceID := "svc_oauth2_min"

	// Minimal payload: token_url + credential_fields only.
	payload := []byte(`{"token_url":"https://example.com/token","credential_fields":{"user":"u","pass":"p"},"token_response_path":"$.access_token"}`)

	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT,
		Value:      payload,
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}

	if string(getResp.Value) != string(payload) {
		t.Errorf("minimal payload round-trip mismatch:\n  stored: %s\n  got:    %s", payload, getResp.Value)
	}
}

// -----------------------------------------------------------------------
// Scope enforcement tests
// -----------------------------------------------------------------------

// newTestGRPCServerWithAuth creates a gRPC server with scope enforcement
// enabled via the scopeInterceptor. Returns a client, the VaultService
// (for registering identities), and a cleanup func.
func newTestGRPCServerWithAuth(t *testing.T) (vaultv1.VaultAdapterClient, *VaultService, func()) {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}
	s, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}

	svc := NewVaultService(kek, s)

	lis := bufconn.Listen(bufSize)
	srv := grpc.NewServer(
		grpc.UnaryInterceptor(scopeInterceptor(svc)),
	)
	vaultv1.RegisterVaultAdapterServer(srv, &grpcVaultServer{svc: svc})

	go func() { _ = srv.Serve(lis) }()

	conn, err := grpc.NewClient(
		"passthrough:///bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return lis.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("grpc.NewClient: %v", err)
	}

	cleanup := func() {
		conn.Close()
		srv.Stop()
		_ = s.Close()
	}
	return vaultv1.NewVaultAdapterClient(conn), svc, cleanup
}

// TestGRPCScopeEnforcement_GetCredential_RequiresVaultRead verifies that
// GetCredential returns PERMISSION_DENIED when the caller lacks vault.read scope.
// Validates: Requirement 22.5.
func TestGRPCScopeEnforcement_GetCredential_RequiresVaultRead(t *testing.T) {
	ctx := context.Background()
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	// Register a service identity with only vault.put scope (no vault.read).
	token := []byte("proxy-token-32-bytes-for-testing!")
	if err := svc.RegisterServiceIdentity("svcid_proxy", token, []string{"vault.put"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	// Store a credential first (using a caller with vault.put scope).
	md := metadata.Pairs(
		"x-mintkey-service-token", string(token),
		"x-mintkey-service-identity", "svcid_proxy",
	)
	putCtx := metadata.NewOutgoingContext(ctx, md)

	_, err := client.PutCredential(putCtx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_scope_test",
		ServiceId:  "svc_scope_test",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("my-secret"),
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	// Attempt GetCredential with the same identity (lacks vault.read).
	_, err = client.GetCredential(putCtx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_scope_test",
		ServiceId:  "svc_scope_test",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED for GetCredential without vault.read scope, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied, got %v: %s", st.Code(), st.Message())
	}
}

// TestGRPCScopeEnforcement_GetCredential_AllowedWithVaultRead verifies that
// GetCredential succeeds when the caller has vault.read scope.
func TestGRPCScopeEnforcement_GetCredential_AllowedWithVaultRead(t *testing.T) {
	ctx := context.Background()
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	// Register identity with both vault.read and vault.put scopes.
	token := []byte("admin-token-32-bytes-for-testing!")
	if err := svc.RegisterServiceIdentity("svcid_admin", token, []string{"vault.read", "vault.put"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	md := metadata.Pairs(
		"x-mintkey-service-token", string(token),
		"x-mintkey-service-identity", "svcid_admin",
	)
	authCtx := metadata.NewOutgoingContext(ctx, md)

	// Store a credential.
	_, err := client.PutCredential(authCtx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_scope_ok",
		ServiceId:  "svc_scope_ok",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT,
		Value:      []byte(`{"token_url":"https://example.com/auth","credential_fields":{"u":"v"},"token_response_path":"$.token"}`),
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	// GetCredential should succeed with vault.read scope.
	getResp, err := client.GetCredential(authCtx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_scope_ok",
		ServiceId:  "svc_scope_ok",
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential with vault.read scope: %v", err)
	}
	if getResp.AuthScheme != vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT {
		t.Errorf("expected auth_scheme=8, got %d", getResp.AuthScheme)
	}
}

// TestGRPCScopeEnforcement_MissingToken verifies that GetCredential returns
// PERMISSION_DENIED when no service token is provided.
func TestGRPCScopeEnforcement_MissingToken(t *testing.T) {
	ctx := context.Background()
	client, _, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	// Call without any metadata.
	_, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_01",
		ServiceId:  "svc_01",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED for missing token, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied, got %v", st.Code())
	}
}

// -----------------------------------------------------------------------
// BUG-20: admin-api identity scope enforcement tests
// -----------------------------------------------------------------------

// TestGRPCScopeEnforcement_AdminAPIIdentity_PutAndGet verifies that
// an identity registered as "svcid_admin_api" with [vault.read, vault.put]
// can successfully call both PutCredential and GetCredential.
// Validates: BUG-20 fix — admin-api must be wired like the proxy-plugin.
func TestGRPCScopeEnforcement_AdminAPIIdentity_PutAndGet(t *testing.T) {
	ctx := context.Background()
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	token := []byte("admin-api-token-32bytes-for-test!")
	if err := svc.RegisterServiceIdentity("svcid_admin_api", token, []string{"vault.read", "vault.put"}); err != nil {
		t.Fatalf("RegisterServiceIdentity svcid_admin_api: %v", err)
	}

	md := metadata.Pairs(
		"x-mintkey-service-token", string(token),
		"x-mintkey-service-identity", "svcid_admin_api",
	)
	authCtx := metadata.NewOutgoingContext(ctx, md)

	// PutCredential must succeed.
	putResp, err := client.PutCredential(authCtx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_admin_api_test",
		ServiceId:  "svc_admin_api_test",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("admin-api-secret"),
	})
	if err != nil {
		t.Fatalf("PutCredential with svcid_admin_api: %v", err)
	}
	if putResp.KeyVersion == 0 {
		t.Errorf("expected non-zero key_version from PutCredential")
	}

	// GetCredential must succeed.
	getResp, err := client.GetCredential(authCtx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_admin_api_test",
		ServiceId:  "svc_admin_api_test",
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential with svcid_admin_api: %v", err)
	}
	if string(getResp.Value) != "admin-api-secret" {
		t.Errorf("GetCredential returned %q, want %q", getResp.Value, "admin-api-secret")
	}
}

// TestGRPCScopeEnforcement_AdminAPIIdentity_PermissionDenied_NoToken verifies
// that calling PutCredential/GetCredential with no token returns PERMISSION_DENIED.
// This is the exact failure mode that BUG-20 fixes.
func TestGRPCScopeEnforcement_AdminAPIIdentity_PermissionDenied_NoToken(t *testing.T) {
	ctx := context.Background()
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	// Register admin-api identity — but don't send its token in the call.
	token := []byte("admin-api-token-32bytes-for-test!")
	if err := svc.RegisterServiceIdentity("svcid_admin_api", token, []string{"vault.read", "vault.put"}); err != nil {
		t.Fatalf("RegisterServiceIdentity svcid_admin_api: %v", err)
	}

	// PutCredential with NO metadata → PERMISSION_DENIED.
	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_noauth",
		ServiceId:  "svc_noauth",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("secret"),
	})
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED for PutCredential without token, got nil")
	}
	if st, ok := status.FromError(err); !ok || st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied for PutCredential, got %v", err)
	}

	// GetCredential with NO metadata → PERMISSION_DENIED.
	_, err = client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_noauth",
		ServiceId:  "svc_noauth",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED for GetCredential without token, got nil")
	}
	if st, ok := status.FromError(err); !ok || st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied for GetCredential, got %v", err)
	}
}

// TestGRPCScopeEnforcement_AdminAPIIdentity_WrongScopeIdentity verifies
// that a caller with a wrong-scope identity gets PERMISSION_DENIED
// on the method requiring the missing scope.
func TestGRPCScopeEnforcement_AdminAPIIdentity_WrongScopeIdentity(t *testing.T) {
	ctx := context.Background()
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	// Register identity with ONLY vault.put — no vault.read.
	token := []byte("put-only-token-32bytes-for-test!!")
	if err := svc.RegisterServiceIdentity("svcid_put_only", token, []string{"vault.put"}); err != nil {
		t.Fatalf("RegisterServiceIdentity svcid_put_only: %v", err)
	}

	md := metadata.Pairs(
		"x-mintkey-service-token", string(token),
		"x-mintkey-service-identity", "svcid_put_only",
	)
	authCtx := metadata.NewOutgoingContext(ctx, md)

	// PutCredential must succeed (has vault.put).
	_, err := client.PutCredential(authCtx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_wrongscope",
		ServiceId:  "svc_wrongscope",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("secret"),
	})
	if err != nil {
		t.Fatalf("PutCredential with put-only identity: %v", err)
	}

	// GetCredential must fail (lacks vault.read).
	_, err = client.GetCredential(authCtx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_wrongscope",
		ServiceId:  "svc_wrongscope",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED for GetCredential with put-only identity, got nil")
	}
	if st, ok := status.FromError(err); !ok || st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied, got %v", err)
	}
}

// contains is a simple substring check (avoids importing strings in test file).
func contains(haystack, needle string) bool {
	if needle == "" {
		return false
	}
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}

// -----------------------------------------------------------------------
// Property-Based Tests — Feature: service-templates
// -----------------------------------------------------------------------

// oauth2PasswordGrantCredential mirrors the JSON structure stored in the Vault
// for auth_scheme=8. It is defined here (not in production code) to keep the
// test self-contained and to assert the round-trip at the struct level.
//
// TokenRequestHeaders is omitempty: when absent or empty-map it is omitted from
// JSON, so generators MUST produce either nil (absent) or a non-empty map.
type oauth2PasswordGrantCredential struct {
	TokenURL            string            `json:"token_url"`
	CredentialFields    map[string]string `json:"credential_fields"`
	TokenResponsePath   string            `json:"token_response_path"`
	TokenRequestHeaders map[string]string `json:"token_request_headers,omitempty"`
}

// drawStringMap generates a non-empty map[string]string with 1–4 entries.
// Keys and values are drawn from a safe printable-ASCII alphabet to avoid
// JSON encoding corner-cases unrelated to the storage round-trip.
func drawStringMap(t *rapid.T, label string) map[string]string {
	alphabet := rapid.StringMatching(`[a-zA-Z0-9_\-\.]{1,20}`)
	size := rapid.IntRange(1, 4).Draw(t, label+"_size")
	m := make(map[string]string, size)
	for i := 0; i < size; i++ {
		k := alphabet.Draw(t, fmt.Sprintf("%s_key_%d", label, i))
		v := alphabet.Draw(t, fmt.Sprintf("%s_val_%d", label, i))
		m[k] = v
	}
	return m
}

// drawOAuth2Credential generates an arbitrary valid OAuth2PasswordGrantCredential.
//
// Validity constraints (from design §4.2 / Property 2):
//   - token_url: non-empty string (PBT does not enforce HTTPS here — that is
//     Property 3's domain; vault storage is scheme-agnostic)
//   - credential_fields: non-empty map
//   - token_response_path: non-empty string
//   - token_request_headers: nil OR a non-empty map (omitempty)
//
// Discriminating power: this generator will produce payloads where
// token_request_headers is present about 50 % of iterations. A serialization
// bug that drops token_request_headers (or any sub-key of credential_fields)
// would cause deep-equal to differ, falsifying the property.
func drawOAuth2Credential(t *rapid.T) oauth2PasswordGrantCredential {
	urlSuffix := rapid.StringMatching(`[a-zA-Z0-9/\-_\.]{1,40}`).Draw(t, "url_suffix")
	tokenURL := "https://auth.example.com/" + urlSuffix

	responsePath := rapid.StringMatching(`\$\.[a-zA-Z0-9_\.]{1,20}`).Draw(t, "response_path")

	credFields := drawStringMap(t, "cred_fields")

	// ~50 % chance of having token_request_headers.
	var headers map[string]string
	if rapid.Bool().Draw(t, "has_headers") {
		headers = drawStringMap(t, "headers")
	}

	return oauth2PasswordGrantCredential{
		TokenURL:            tokenURL,
		CredentialFields:    credFields,
		TokenResponsePath:   responsePath,
		TokenRequestHeaders: headers,
	}
}

// TestCredentialStorageRoundTrip is the rapid PBT for Property 2.
//
// Feature: service-templates, Property 2: Credential storage round-trip
//
// For any valid OAuth2PasswordGrantCredential payload, storing via PutCredential
// then retrieving via GetCredential yields a JSON-decoded structure IDENTICAL to
// the original. The test exercises the REAL scoped gRPC path: PutCredential
// requires vault.put; GetCredential requires vault.read.
//
// Discriminating power: the property would be falsified by (among others):
//   - A serialization layer that drops token_request_headers (omitempty + empty
//     map confusion — e.g., storing {} then retrieving nil would differ).
//   - A layer that drops any credential_fields key.
//   - Any field truncation, key re-ordering that produces a different decoded struct.
//
// Validates: Requirements 19.3.
func TestCredentialStorageRoundTrip(t *testing.T) {
	// Stand up a scoped gRPC server (with scopeInterceptor) once; reuse across
	// all rapid iterations to avoid per-iteration setup overhead.
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	// Register a single service identity with both scopes.
	const identityID = "pbt_identity_roundtrip"
	token := []byte("pbt-roundtrip-token-32bytes-xxxxx")
	if err := svc.RegisterServiceIdentity(identityID, token, []string{"vault.put", "vault.read"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}
	md := metadata.Pairs(
		"x-mintkey-service-token", string(token),
		"x-mintkey-service-identity", identityID,
	)
	authCtx := metadata.NewOutgoingContext(context.Background(), md)

	// Use a counter to give each iteration a unique (tenantID, serviceID) pair
	// so credentials from different iterations don't collide inside the store.
	var iteration int

	rapid.Check(t, func(rt *rapid.T) {
		iteration++
		tenantID := fmt.Sprintf("pbt_tenant_%d", iteration)
		serviceID := fmt.Sprintf("pbt_service_%d", iteration)

		// Draw an arbitrary valid credential.
		original := drawOAuth2Credential(rt)

		// Encode to JSON — this is what the caller would send as the Value bytes.
		payloadBytes, err := json.Marshal(original)
		if err != nil {
			rt.Fatalf("json.Marshal original: %v", err)
		}

		// PUT — requires vault.put scope.
		putResp, err := client.PutCredential(authCtx, &vaultv1.PutCredentialRequest{
			TenantId:   tenantID,
			ServiceId:  serviceID,
			AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT,
			Value:      payloadBytes,
		})
		if err != nil {
			rt.Fatalf("PutCredential: %v", err)
		}
		if putResp.KeyVersion == 0 {
			rt.Fatalf("expected non-zero key_version from PutCredential")
		}

		// GET — requires vault.read scope.
		getResp, err := client.GetCredential(authCtx, &vaultv1.GetCredentialRequest{
			TenantId:   tenantID,
			ServiceId:  serviceID,
			KeyVersion: 0, // current
		})
		if err != nil {
			rt.Fatalf("GetCredential: %v", err)
		}

		// Invariant: auth_scheme must be preserved.
		if getResp.AuthScheme != vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT {
			rt.Fatalf("auth_scheme mismatch: got %d, want %d",
				getResp.AuthScheme, vaultv1.AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT)
		}

		// Decode the retrieved bytes back into the struct.
		var retrieved oauth2PasswordGrantCredential
		if err := json.Unmarshal(getResp.Value, &retrieved); err != nil {
			rt.Fatalf("json.Unmarshal retrieved: %v (raw: %q)", err, getResp.Value)
		}

		// Deep-equal invariant: decoded retrieved == original stored.
		// reflect.DeepEqual on map[string]string is order-independent.
		if !reflect.DeepEqual(original, retrieved) {
			rt.Fatalf("round-trip mismatch:\n  stored:    %+v\n  retrieved: %+v\n  raw bytes in: %s\n  raw bytes out: %s",
				original, retrieved, payloadBytes, getResp.Value)
		}
	})
}

// -----------------------------------------------------------------------
// AUTH_SCHEME_APPLE_JWT handler tests
// -----------------------------------------------------------------------

// mustTestECKeyPEM generates a P-256 ECDSA key and returns it PEM-encoded as
// PKCS#8. Mirrors the helper in applejwt/generate_test.go but scoped to the
// server test package (cross-package test helpers cannot be shared in Go).
func mustTestECKeyPEM(t *testing.T) ([]byte, *ecdsa.PrivateKey) {
	t.Helper()
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate EC key: %v", err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		t.Fatalf("marshal PKCS8: %v", err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
	return pemBytes, priv
}

// TestGRPCAppleJWT_HappyPath stores an apple_jwt JSON envelope via PutCredential
// (auth_scheme=9), then calls GetCredential and verifies:
//   - The returned Value is a valid ES256 JWS (three dot-separated segments).
//   - The JWT verifies with the original EC public key.
//   - iss == issuerID.
//   - aud contains "appstoreconnect-v1".
//   - AuthScheme in the response is AUTH_SCHEME_APPLE_JWT.
func TestGRPCAppleJWT_HappyPath(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	pemBytes, ecPriv := mustTestECKeyPEM(t)

	const keyID = "TESTKEY0001"
	const issuerID = "11111111-2222-3333-4444-555555555555"

	envelope := appleJWTEnvelope{
		Scheme:   "apple_jwt",
		P8KeyPEM: string(pemBytes),
		KeyID:    keyID,
		IssuerID: issuerID,
	}
	envelopeBytes, err := json.Marshal(envelope)
	if err != nil {
		t.Fatalf("marshal envelope: %v", err)
	}

	// Store the envelope.
	putResp, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_apple_jwt",
		ServiceId:  "svc_apple_jwt",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_APPLE_JWT,
		Value:      envelopeBytes,
	})
	if err != nil {
		t.Fatalf("PutCredential (apple_jwt): %v", err)
	}
	if putResp.KeyVersion == 0 {
		t.Fatal("expected non-zero key_version")
	}

	// Retrieve — handler must generate a fresh JWT.
	getResp, err := client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_apple_jwt",
		ServiceId:  "svc_apple_jwt",
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential (apple_jwt): %v", err)
	}

	// AuthScheme must be preserved.
	if getResp.AuthScheme != vaultv1.AuthScheme_AUTH_SCHEME_APPLE_JWT {
		t.Errorf("AuthScheme = %v, want AUTH_SCHEME_APPLE_JWT", getResp.AuthScheme)
	}

	// The returned Value must be a non-empty JWS string.
	jwtStr := string(getResp.Value)
	if jwtStr == "" {
		t.Fatal("GetCredential returned empty Value for apple_jwt")
	}

	// Parse and verify the JWT with the original EC public key.
	parsedJWT, err := josejwt.ParseSigned(jwtStr, []jose.SignatureAlgorithm{jose.ES256})
	if err != nil {
		t.Fatalf("ParseSigned on returned Value: %v (raw: %q)", err, jwtStr)
	}

	// Verify signature + extract claims.
	var claims josejwt.Claims
	if err := parsedJWT.Claims(ecPriv.Public(), &claims); err != nil {
		t.Fatalf("verify+extract claims: %v", err)
	}

	if claims.Issuer != issuerID {
		t.Errorf("iss = %q, want %q", claims.Issuer, issuerID)
	}
	if len(claims.Audience) != 1 || claims.Audience[0] != "appstoreconnect-v1" {
		t.Errorf("aud = %v, want [appstoreconnect-v1]", claims.Audience)
	}

	// Confirm the raw stored envelope is NOT returned (value should not be valid JSON).
	var leak appleJWTEnvelope
	if json.Unmarshal(getResp.Value, &leak) == nil && leak.P8KeyPEM != "" {
		t.Error("SECURITY: GetCredential leaked the raw apple_jwt JSON envelope (p8_key_pem visible)")
	}
}

// TestGRPCAppleJWT_EmptyP8KeyPEM verifies that an envelope missing p8_key_pem
// returns codes.InvalidArgument (not Internal), with a terse message that
// does not include key material.
func TestGRPCAppleJWT_EmptyP8KeyPEM(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	// Envelope with empty p8_key_pem — invalid.
	envelope := appleJWTEnvelope{
		Scheme:   "apple_jwt",
		P8KeyPEM: "", // intentionally empty
		KeyID:    "TESTKEY0001",
		IssuerID: "11111111-2222-3333-4444-555555555555",
	}
	envelopeBytes, _ := json.Marshal(envelope)

	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_apple_jwt_bad",
		ServiceId:  "svc_apple_jwt_bad",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_APPLE_JWT,
		Value:      envelopeBytes,
	})
	if err != nil {
		t.Fatalf("PutCredential unexpected error: %v", err)
	}

	_, err = client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_apple_jwt_bad",
		ServiceId:  "svc_apple_jwt_bad",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected error for envelope with empty p8_key_pem, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.InvalidArgument {
		t.Errorf("expected codes.InvalidArgument, got %v: %s", st.Code(), st.Message())
	}
}

// -----------------------------------------------------------------------
// ValidateServiceIdentity handler tests
// -----------------------------------------------------------------------

// TestGRPCValidateServiceIdentity_HappyPath verifies that a registered identity
// with valid token in gRPC metadata returns ok=true and the correct scopes.
func TestGRPCValidateServiceIdentity_HappyPath(t *testing.T) {
	ctx := context.Background()
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	token := []byte("email-proxy-token-32bytes-xxxxxx")
	if err := svc.RegisterServiceIdentity("svcid_email_proxy", token, []string{"vault.read"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	md := metadata.Pairs(
		"x-mintkey-service-identity", "svcid_email_proxy",
		"x-mintkey-service-token", string(token),
	)
	authCtx := metadata.NewOutgoingContext(ctx, md)

	resp, err := client.ValidateServiceIdentity(authCtx, &vaultv1.ValidateServiceIdentityRequest{})
	if err != nil {
		t.Fatalf("ValidateServiceIdentity: %v", err)
	}
	if !resp.Ok {
		t.Errorf("expected ok=true, got false")
	}
	if len(resp.Scopes) != 1 || resp.Scopes[0] != "vault.read" {
		t.Errorf("expected scopes=[vault.read], got %v", resp.Scopes)
	}
}

// TestGRPCValidateServiceIdentity_MissingToken verifies that a call without any
// service-identity metadata returns codes.Unauthenticated.
func TestGRPCValidateServiceIdentity_MissingToken(t *testing.T) {
	ctx := context.Background()
	client, _, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	_, err := client.ValidateServiceIdentity(ctx, &vaultv1.ValidateServiceIdentityRequest{})
	if err == nil {
		t.Fatal("expected error for missing token, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.Unauthenticated {
		t.Errorf("expected codes.Unauthenticated, got %v", st.Code())
	}
}

// TestGRPCValidateServiceIdentity_WrongToken verifies that a registered identity
// with the wrong token in metadata returns codes.PermissionDenied.
func TestGRPCValidateServiceIdentity_WrongToken(t *testing.T) {
	ctx := context.Background()
	client, svc, cleanup := newTestGRPCServerWithAuth(t)
	defer cleanup()

	goodToken := []byte("email-proxy-token-32bytes-xxxxxx")
	if err := svc.RegisterServiceIdentity("svcid_email_proxy", goodToken, []string{"vault.read"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	md := metadata.Pairs(
		"x-mintkey-service-identity", "svcid_email_proxy",
		"x-mintkey-service-token", "wrong-token-that-does-not-match!",
	)
	authCtx := metadata.NewOutgoingContext(ctx, md)

	_, err := client.ValidateServiceIdentity(authCtx, &vaultv1.ValidateServiceIdentityRequest{})
	if err == nil {
		t.Fatal("expected error for wrong token, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied, got %v", st.Code())
	}
}

// TestGRPCAppleJWT_WrongSchemeField verifies that an envelope with scheme != "apple_jwt"
// returns codes.InvalidArgument.
func TestGRPCAppleJWT_WrongSchemeField(t *testing.T) {
	ctx := context.Background()
	client, cleanup := newTestGRPCServer(t)
	defer cleanup()

	pemBytes, _ := mustTestECKeyPEM(t)
	envelope := appleJWTEnvelope{
		Scheme:   "bearer_token", // wrong scheme field
		P8KeyPEM: string(pemBytes),
		KeyID:    "TESTKEY0001",
		IssuerID: "11111111-2222-3333-4444-555555555555",
	}
	envelopeBytes, _ := json.Marshal(envelope)

	_, err := client.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   "tenant_apple_jwt_wrongscheme",
		ServiceId:  "svc_apple_jwt_wrongscheme",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_APPLE_JWT,
		Value:      envelopeBytes,
	})
	if err != nil {
		t.Fatalf("PutCredential unexpected error: %v", err)
	}

	_, err = client.GetCredential(ctx, &vaultv1.GetCredentialRequest{
		TenantId:   "tenant_apple_jwt_wrongscheme",
		ServiceId:  "svc_apple_jwt_wrongscheme",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected InvalidArgument for wrong scheme field, got nil")
	}
	st, _ := status.FromError(err)
	if st.Code() != codes.InvalidArgument {
		t.Errorf("expected codes.InvalidArgument, got %v", st.Code())
	}
}
