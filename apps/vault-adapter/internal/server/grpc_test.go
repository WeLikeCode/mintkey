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
	"net"
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
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
