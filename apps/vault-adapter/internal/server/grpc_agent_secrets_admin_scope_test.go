// Package server — focused scope test for svcid_admin_api (ADR-0025 C3).
//
// Verifies least-privilege enforcement:
//   - svcid_admin_api holds vault.secret.put + vault.secret.delete.
//   - PutAgentSecret and DeleteAgentSecret succeed for svcid_admin_api.
//   - GetAgentSecret returns PERMISSION_DENIED for svcid_admin_api
//     (vault.secret.read is NOT granted to admin-api).
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
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

const adminScopeTestBufSize = 1024 * 1024

// newAdminScopeTestServer spins up an in-process gRPC server with:
//   - svcid_mcp      → vault.secret.put, vault.secret.read, vault.secret.delete
//   - svcid_admin_api → vault.secret.put, vault.secret.delete (NO read)
func newAdminScopeTestServer(t *testing.T) (vaultv1.AgentSecretsVaultClient, func()) {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 7)
	}

	credStore, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}

	svc := NewVaultService(kek, credStore)

	if err := svc.RegisterServiceIdentity("svcid_mcp", []byte("test-mcp-token-32byteslong!!!!!!"), []string{
		"vault.secret.put", "vault.secret.read", "vault.secret.delete",
	}); err != nil {
		t.Fatalf("RegisterServiceIdentity(mcp): %v", err)
	}
	// svcid_admin_api: put+delete, NOT read — least privilege.
	if err := svc.RegisterServiceIdentity("svcid_admin_api", []byte("test-admin-token-32byteslong!!!!"), []string{
		"vault.secret.put", "vault.secret.delete",
	}); err != nil {
		t.Fatalf("RegisterServiceIdentity(admin_api): %v", err)
	}

	fakeStore := newFakeAgentSecretStore()

	lis := bufconn.Listen(adminScopeTestBufSize)
	grpcSrv := grpc.NewServer(grpc.UnaryInterceptor(scopeInterceptor(svc)))
	vaultv1.RegisterVaultAdapterServer(grpcSrv, &grpcVaultServer{svc: svc})
	RegisterAgentSecretsVaultServer(grpcSrv, svc, fakeStore)

	go func() { _ = grpcSrv.Serve(lis) }()

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
		grpcSrv.Stop()
		_ = credStore.Close()
	}
	return vaultv1.NewAgentSecretsVaultClient(conn), cleanup
}

// TestAdminApiScope_PutAgentSecret_Allowed verifies svcid_admin_api can call PutAgentSecret.
func TestAdminApiScope_PutAgentSecret_Allowed(t *testing.T) {
	client, cleanup := newAdminScopeTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_admin_api", "test-admin-token-32byteslong!!!!")

	_, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
		TenantId: "t_tenant01",
		SecretId: "sec_admin01",
		Value:    []byte("admin-provisioned-secret"),
	})
	if err != nil {
		t.Fatalf("PutAgentSecret: expected OK, got %v", err)
	}
}

// TestAdminApiScope_DeleteAgentSecret_Allowed verifies svcid_admin_api can call DeleteAgentSecret.
func TestAdminApiScope_DeleteAgentSecret_Allowed(t *testing.T) {
	client, cleanup := newAdminScopeTestServer(t)
	defer cleanup()

	// First put via mcp identity so there is a row to delete.
	mcpCtx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")
	if _, err := client.PutAgentSecret(mcpCtx, &vaultv1.PutAgentSecretRequest{
		TenantId: "t_tenant01",
		SecretId: "sec_del01",
		Value:    []byte("to-be-deleted"),
	}); err != nil {
		t.Fatalf("PutAgentSecret (setup): %v", err)
	}

	ctx := mdWithIdentity(context.Background(), "svcid_admin_api", "test-admin-token-32byteslong!!!!")
	resp, err := client.DeleteAgentSecret(ctx, &vaultv1.DeleteAgentSecretRequest{
		TenantId: "t_tenant01",
		SecretId: "sec_del01",
	})
	if err != nil {
		t.Fatalf("DeleteAgentSecret: expected OK, got %v", err)
	}
	if !resp.GetDeleted() {
		t.Error("DeleteAgentSecret: expected deleted=true for existing row")
	}
}

// TestAdminApiScope_GetAgentSecret_Denied verifies svcid_admin_api cannot call GetAgentSecret.
// vault.secret.read is NOT granted — operators never read agent-secret plaintext.
func TestAdminApiScope_GetAgentSecret_Denied(t *testing.T) {
	client, cleanup := newAdminScopeTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_admin_api", "test-admin-token-32byteslong!!!!")

	_, err := client.GetAgentSecret(ctx, &vaultv1.GetAgentSecretRequest{
		TenantId: "t_tenant01",
		SecretId: "sec_admin01",
	})
	if err == nil {
		t.Fatal("GetAgentSecret: expected PERMISSION_DENIED, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.PermissionDenied {
		t.Errorf("GetAgentSecret: want PermissionDenied, got %v", s.Code())
	}
}
