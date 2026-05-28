// Package vault_test — cross-module integration test for BUG-1 (Requirement 22.5).
//
// This test drives the PRODUCTION path:
//
//	apps/proxy-plugin/internal/vault.Client.GetCredential
//
// against a REAL vault-adapter server running the REAL scopeInterceptor, started
// via vaulttest.Start which calls VaultServer.ListenAndServe — the same code
// path used in production.
//
// Both sub-tests use vault.NewClient verbatim; no mocks, no hand-built gRPC
// metadata, no t.Skip.
//
//   - TestBug1_CrossModule_EmptyTokenPermissionDenied: NewClient("","") → PERMISSION_DENIED.
//   - TestBug1_CrossModule_CorrectTokenSucceeds:        NewClient(token,id) → success.
//
// Source: remediation/active/2026-05-28-service-templates-adversarial/
//
//	00-findings-and-intake.md BUG-1 (FAIL-2 correction).
package vault_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
	"github.com/mintkey/mintkey/services/vault-adapter/vaulttest"
	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

const (
	// devProxyToken is the shared secret provisioned in
	// infra/compose/docker-compose.yml for both services.  32 bytes / 256 bits.
	devProxyToken      = "mk_vault_proxy_dev_secret_32b!!!!"
	devProxyIdentityID = "svcid_proxy"
)

// seedTestCredential seeds a credential into the running vault-adapter so
// GetCredential has something to return.  PutCredential is not guarded by
// scope (vault.put is granted), but we must still present a valid identity.
func seedTestCredential(t *testing.T, addr, tenantID, serviceID string) {
	t.Helper()
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("seed grpc.NewClient: %v", err)
	}
	defer conn.Close()

	md := metadata.Pairs(
		"x-mintkey-service-token", devProxyToken,
		"x-mintkey-service-identity", devProxyIdentityID,
	)
	ctx := metadata.NewOutgoingContext(context.Background(), md)
	stub := vaultv1.NewVaultAdapterClient(conn)
	_, err = stub.PutCredential(ctx, &vaultv1.PutCredentialRequest{
		TenantId:   tenantID,
		ServiceId:  serviceID,
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte("integration-test-secret"),
	})
	if err != nil {
		t.Fatalf("seed PutCredential(%s/%s): %v", tenantID, serviceID, err)
	}
}

// TestBug1_CrossModule_EmptyTokenPermissionDenied proves that the production
// vault.Client constructed with an empty token (the pre-fix state when
// MINTKEY_VAULT_PROXY_TOKEN was unset and defaulted to "") returns an error
// containing PERMISSION_DENIED from the real scopeInterceptor.
//
// This is the "red" half: without provisioning, every proxy credential fetch fails.
func TestBug1_CrossModule_EmptyTokenPermissionDenied(t *testing.T) {
	srv, err := vaulttest.Start(
		devProxyIdentityID,
		[]byte(devProxyToken),
		[]string{"vault.read", "vault.put"},
	)
	if err != nil {
		t.Fatalf("vaulttest.Start: %v", err)
	}
	defer srv.Stop()

	seedTestCredential(t, srv.Addr, "tenant1", "svc1")

	// Pre-fix / unprovisioned: NewClient with empty token and no identity ID.
	// This is what proxy-plugin/cmd/proxy-plugin/main.go produced when
	// MINTKEY_VAULT_PROXY_TOKEN was unset (defaulted to "").
	buggyClient := vault.NewClient(srv.Addr, "", "")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err = buggyClient.GetCredential(ctx, vault.GetCredentialRequest{
		TenantID:  "tenant1",
		ServiceID: "svc1",
	})
	if err == nil {
		t.Fatal("BUG-1 regression: expected error with empty token via production client, got nil")
	}
	// vault.Client wraps the gRPC error; check for PermissionDenied in message.
	errMsg := err.Error()
	if !strings.Contains(errMsg, "PermissionDenied") &&
		!strings.Contains(errMsg, "permission denied") &&
		!strings.Contains(errMsg, "PERMISSION_DENIED") {
		t.Errorf("expected PermissionDenied in error, got: %v", err)
	}
	t.Logf("BUG-1 cross-module confirmed: empty-token production client → %v", err)
}

// TestBug1_CrossModule_CorrectTokenSucceeds proves that the production
// vault.Client constructed with the correct identity+token (as provisioned in
// infra/compose/docker-compose.yml via MINTKEY_VAULT_PROXY_TOKEN) succeeds
// through the real scopeInterceptor.
//
// This is the "green" half: with correct provisioning the proxy credential
// fetch succeeds end-to-end.
func TestBug1_CrossModule_CorrectTokenSucceeds(t *testing.T) {
	srv, err := vaulttest.Start(
		devProxyIdentityID,
		[]byte(devProxyToken),
		[]string{"vault.read", "vault.put"},
	)
	if err != nil {
		t.Fatalf("vaulttest.Start: %v", err)
	}
	defer srv.Stop()

	seedTestCredential(t, srv.Addr, "tenant2", "svc2")

	// Fixed client: vault.NewClient with the dev token and identity ID that
	// compose provisions via MINTKEY_VAULT_PROXY_TOKEN / MINTKEY_VAULT_PROXY_IDENTITY_ID.
	// This is exactly what proxy-plugin/cmd/proxy-plugin/main.go:79 does:
	//   vault.NewClient(cfg.VaultAddrGRPC, cfg.VaultIdentityToken, cfg.VaultIdentityID)
	fixedClient := vault.NewClient(srv.Addr, devProxyToken, devProxyIdentityID)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := fixedClient.GetCredential(ctx, vault.GetCredentialRequest{
		TenantID:  "tenant2",
		ServiceID: "svc2",
	})
	if err != nil {
		t.Fatalf("BUG-1 fix regression: production NewClient with correct identity+token failed: %v", err)
	}
	if string(resp.Plaintext) != "integration-test-secret" {
		t.Errorf("expected plaintext %q, got %q", "integration-test-secret", resp.Plaintext)
	}
	t.Logf("BUG-1 fix verified: production NewClient with correct identity+token → success, plaintext=%q", resp.Plaintext)
}
