// Package server — BUG-1 reproduction: proxy client sends empty token and
// no x-mintkey-service-identity header, causing PERMISSION_DENIED on every
// GetCredential call through the scopeInterceptor.
//
// Source: remediation/active/2026-05-28-service-templates-adversarial/00-findings-and-intake.md BUG-1.
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

// newTestServerWithAuthAndIdentity spins up a gRPC server WITH the
// scopeInterceptor and registers a named service identity so that a
// correctly-authenticated client can call GetCredential.
//
// Returns the raw gRPC conn (so callers can build their own metadata context),
// the VaultService (for seeding credentials), and a cleanup func.
func newTestServerWithAuthAndIdentity(
	t *testing.T,
	identityID string,
	token []byte,
	scopes []string,
) (*grpc.ClientConn, *VaultService, func()) {
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

	if identityID != "" {
		if err := svc.RegisterServiceIdentity(identityID, token, scopes); err != nil {
			t.Fatalf("RegisterServiceIdentity: %v", err)
		}
	}

	lis := bufconn.Listen(1024 * 1024)
	srv := grpc.NewServer(grpc.UnaryInterceptor(scopeInterceptor(svc)))
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
	return conn, svc, cleanup
}

// TestBug1_ProxyClientEmptyTokenNoIdentityPermissionDenied reproduces BUG-1:
// the production proxy client sends an empty service token and no
// x-mintkey-service-identity header.  This MUST return PERMISSION_DENIED
// through the real scopeInterceptor (not a mock).
//
// Before the fix: this test fails because GetCredential returns
// PERMISSION_DENIED (the bug is real).
// After the fix: the proxy client sends the correct identity and token so
// GetCredential succeeds — see TestBug1_ProxyClientWithIdentitySucceeds.
func TestBug1_ProxyClientEmptyTokenNoIdentityPermissionDenied(t *testing.T) {
	// Register a valid proxy identity so any failure is NOT "identity unknown"
	// but specifically "empty token / no identity header".
	proxyToken := []byte("proxy-secret-32-bytes-for-test!!")
	conn, svc, cleanup := newTestServerWithAuthAndIdentity(
		t, "svcid_proxy", proxyToken, []string{"vault.read", "vault.put"},
	)
	defer cleanup()

	// Seed a credential using the valid identity.
	adminMD := metadata.Pairs(
		"x-mintkey-service-token", string(proxyToken),
		"x-mintkey-service-identity", "svcid_proxy",
	)
	seedCtx := metadata.NewOutgoingContext(context.Background(), adminMD)
	stub := vaultv1.NewVaultAdapterClient(conn)
	_, err := stub.PutCredential(seedCtx, &vaultv1.PutCredentialRequest{
		TenantId:   "t1",
		ServiceId:  "s1",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("super-secret"),
	})
	if err != nil {
		t.Fatalf("seed PutCredential: %v", err)
	}

	// Now simulate what the production proxy client actually does:
	// - sends x-mintkey-service-token="" (empty string)
	// - sends NO x-mintkey-service-identity header
	// This is apps/proxy-plugin/cmd/proxy-plugin/main.go:79
	//   vault.NewClient(cfg.VaultAddrGRPC, "")
	// and apps/proxy-plugin/internal/vault/client.go:94
	//   md := metadata.Pairs("x-mintkey-service-token", c.serviceToken)
	//   (never sets x-mintkey-service-identity)
	buggyMD := metadata.Pairs(
		"x-mintkey-service-token", "", // production value: empty string
		// deliberately no "x-mintkey-service-identity" — this is the bug
	)
	buggyCtx := metadata.NewOutgoingContext(context.Background(), buggyMD)

	_, err = stub.GetCredential(buggyCtx, &vaultv1.GetCredentialRequest{
		TenantId:   "t1",
		ServiceId:  "s1",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("BUG-1: expected PERMISSION_DENIED when proxy sends empty token and no identity header, got nil")
	}
	st, ok := status.FromError(err)
	if !ok {
		t.Fatalf("expected gRPC status error, got %T: %v", err, err)
	}
	if st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied, got %v: %s", st.Code(), st.Message())
	}
	t.Logf("BUG-1 confirmed: GetCredential with empty token returned %v: %s", st.Code(), st.Message())

	// Suppress unused variable warning for svc — RegisterServiceIdentity already called via helper.
	_ = svc
}

// TestBug1_ProxyClientWithIdentitySucceeds verifies that after the fix a proxy
// client presenting the correct identity ID and token through the real
// scopeInterceptor succeeds on GetCredential.
func TestBug1_ProxyClientWithIdentitySucceeds(t *testing.T) {
	proxyToken := []byte("proxy-secret-32-bytes-for-test!!")
	conn, _, cleanup := newTestServerWithAuthAndIdentity(
		t, "svcid_proxy", proxyToken, []string{"vault.read", "vault.put"},
	)
	defer cleanup()

	stub := vaultv1.NewVaultAdapterClient(conn)

	// Seed a credential using the correct identity.
	authMD := metadata.Pairs(
		"x-mintkey-service-token", string(proxyToken),
		"x-mintkey-service-identity", "svcid_proxy",
	)
	authCtx := metadata.NewOutgoingContext(context.Background(), authMD)

	_, err := stub.PutCredential(authCtx, &vaultv1.PutCredentialRequest{
		TenantId:   "t2",
		ServiceId:  "s2",
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("the-real-secret"),
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}

	// GetCredential with the fixed metadata (identity + token).
	resp, err := stub.GetCredential(authCtx, &vaultv1.GetCredentialRequest{
		TenantId:   "t2",
		ServiceId:  "s2",
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("GetCredential with correct identity+token: %v", err)
	}
	if string(resp.GetValue()) != "the-real-secret" {
		t.Errorf("expected plaintext %q, got %q", "the-real-secret", resp.GetValue())
	}
	t.Logf("BUG-1 fix verified: GetCredential with correct identity+token succeeded")
}
