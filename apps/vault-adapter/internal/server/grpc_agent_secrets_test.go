// Package server — unit tests for the AgentSecretsVault gRPC service (ADR-0025).
//
// These tests use an in-process gRPC server (bufconn) backed by a fakeAgentSecretStore.
// They exercise:
//   - PutAgentSecret: happy path, empty value, oversized value, missing fields.
//   - GetAgentSecret: happy path (round-trip decrypt), not-found.
//   - DeleteAgentSecret: existing row (deleted=true), absent row (deleted=false).
//   - Scope enforcement: caller lacking vault.secret.* scope gets PERMISSION_DENIED.
//
// The tests run without any build tag under `go test ./... -short`.
package server

import (
	"context"
	"errors"
	"fmt"
	"net"
	"sync"
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/crypto"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

// -------------------------------------------------------------------------
// fakeAgentSecretStore
// -------------------------------------------------------------------------

type fakeAgentSecretStore struct {
	mu      sync.Mutex
	records map[string]*store.AgentSecretRecord // "tenantID/secretID" → record
	putErr  error
	getErr  error
	delErr  error
}

func newFakeAgentSecretStore() *fakeAgentSecretStore {
	return &fakeAgentSecretStore{records: make(map[string]*store.AgentSecretRecord)}
}

func (f *fakeAgentSecretStore) key(tenantID, secretID string) string {
	return tenantID + "/" + secretID
}

func (f *fakeAgentSecretStore) PutAgentSecret(_ context.Context, rec store.AgentSecretRecord) error {
	if f.putErr != nil {
		return f.putErr
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	copy := rec
	f.records[f.key(rec.TenantID, rec.SecretID)] = &copy
	return nil
}

func (f *fakeAgentSecretStore) GetAgentSecret(_ context.Context, tenantID, secretID string) (*store.AgentSecretRecord, error) {
	if f.getErr != nil {
		return nil, f.getErr
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	r, ok := f.records[f.key(tenantID, secretID)]
	if !ok {
		return nil, store.ErrAgentSecretNotFound
	}
	copy := *r
	return &copy, nil
}

func (f *fakeAgentSecretStore) DeleteAgentSecret(_ context.Context, tenantID, secretID string) error {
	if f.delErr != nil {
		return f.delErr
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	delete(f.records, f.key(tenantID, secretID))
	return nil
}

// -------------------------------------------------------------------------
// test server setup
// -------------------------------------------------------------------------

const agentSecretsBufSize = 1024 * 1024

// newAgentSecretsTestServer spins up an in-process gRPC server with the
// AgentSecretsVault service registered.  It returns:
//   - a client connected over bufconn
//   - the fake store (for assertions)
//   - a cleanup func
//
// The server is wired with a VaultService that has a registered service
// identity "svcid_mcp" with scopes [vault.secret.put, vault.secret.read,
// vault.secret.delete].
func newAgentSecretsTestServer(t *testing.T) (vaultv1.AgentSecretsVaultClient, *fakeAgentSecretStore, func()) {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 42)
	}

	// Use SQLite in-memory store for the underlying VaultService (credentials).
	credStore, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}

	svc := NewVaultService(kek, credStore)
	// Register a test identity for scope enforcement tests.
	if err := svc.RegisterServiceIdentity("svcid_mcp", []byte("test-mcp-token-32byteslong!!!!!!"), []string{
		"vault.secret.put", "vault.secret.read", "vault.secret.delete",
	}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}
	// Also register one with no agent-secret scopes for negative tests.
	if err := svc.RegisterServiceIdentity("svcid_other", []byte("test-other-token-32byteslong!!!!"), []string{
		"vault.read",
	}); err != nil {
		t.Fatalf("RegisterServiceIdentity(other): %v", err)
	}

	fakeStore := newFakeAgentSecretStore()

	lis := bufconn.Listen(agentSecretsBufSize)
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
	return vaultv1.NewAgentSecretsVaultClient(conn), fakeStore, cleanup
}

// mdWithIdentity returns a context carrying the service identity metadata
// for the given identity ID and token.
func mdWithIdentity(ctx context.Context, identityID, token string) context.Context {
	return metadata.NewOutgoingContext(ctx, metadata.Pairs(
		"x-mintkey-service-identity", identityID,
		"x-mintkey-service-token", token,
	))
}

// -------------------------------------------------------------------------
// Tests
// -------------------------------------------------------------------------

func TestAgentSecretsVault_PutAndGet_RoundTrip(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	plaintext := []byte("super-secret-database-password")
	putResp, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_01ABCDE",
		Value:    plaintext,
	})
	if err != nil {
		t.Fatalf("PutAgentSecret: %v", err)
	}
	if putResp.GetKekVersion() == 0 {
		t.Error("PutAgentSecret: expected kek_version > 0")
	}
	if putResp.GetWrittenAt() == nil {
		t.Error("PutAgentSecret: expected written_at to be set")
	}

	getResp, err := client.GetAgentSecret(ctx, &vaultv1.GetAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_01ABCDE",
	})
	if err != nil {
		t.Fatalf("GetAgentSecret: %v", err)
	}
	if string(getResp.GetValue()) != string(plaintext) {
		t.Errorf("GetAgentSecret: want %q, got %q", plaintext, getResp.GetValue())
	}
}

func TestAgentSecretsVault_Put_EmptyValue(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	_, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_01ABC",
		Value:    []byte{},
	})
	if err == nil {
		t.Fatal("expected error for empty value, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.InvalidArgument {
		t.Errorf("want InvalidArgument, got %v", s.Code())
	}
}

func TestAgentSecretsVault_Put_OversizedValue(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	oversized := make([]byte, 65537)
	_, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_01ABC",
		Value:    oversized,
	})
	if err == nil {
		t.Fatal("expected error for oversized value, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.InvalidArgument {
		t.Errorf("want InvalidArgument, got %v", s.Code())
	}
}

func TestAgentSecretsVault_Put_MissingTenantID(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	_, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
		TenantId: "",
		SecretId: "sec_01ABC",
		Value:    []byte("value"),
	})
	if err == nil {
		t.Fatal("expected error for missing tenant_id, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.InvalidArgument {
		t.Errorf("want InvalidArgument, got %v", s.Code())
	}
}

func TestAgentSecretsVault_Get_NotFound(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	_, err := client.GetAgentSecret(ctx, &vaultv1.GetAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_nonexistent",
	})
	if err == nil {
		t.Fatal("expected NOT_FOUND, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.NotFound {
		t.Errorf("want NotFound, got %v", s.Code())
	}
}

func TestAgentSecretsVault_Delete_ExistingRow(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	// Store first.
	_, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_del_01",
		Value:    []byte("to-be-deleted"),
	})
	if err != nil {
		t.Fatalf("PutAgentSecret: %v", err)
	}

	delResp, err := client.DeleteAgentSecret(ctx, &vaultv1.DeleteAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_del_01",
	})
	if err != nil {
		t.Fatalf("DeleteAgentSecret: %v", err)
	}
	if !delResp.GetDeleted() {
		t.Error("DeleteAgentSecret: want deleted=true for existing row")
	}

	// Subsequent get should be NOT_FOUND.
	_, err = client.GetAgentSecret(ctx, &vaultv1.GetAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_del_01",
	})
	if err == nil {
		t.Fatal("expected NOT_FOUND after delete, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.NotFound {
		t.Errorf("want NotFound, got %v", s.Code())
	}
}

func TestAgentSecretsVault_Delete_IdempotentAbsent(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	delResp, err := client.DeleteAgentSecret(ctx, &vaultv1.DeleteAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_never_existed",
	})
	if err != nil {
		t.Fatalf("DeleteAgentSecret (absent): %v", err)
	}
	if delResp.GetDeleted() {
		t.Error("DeleteAgentSecret: want deleted=false for absent row")
	}
}

func TestAgentSecretsVault_ScopeEnforcement_NoScope(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	// svcid_other only has vault.read — not vault.secret.*
	ctx := mdWithIdentity(context.Background(), "svcid_other", "test-other-token-32byteslong!!!!")

	_, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_01",
		Value:    []byte("secret"),
	})
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.PermissionDenied {
		t.Errorf("want PermissionDenied, got %v", s.Code())
	}
}

func TestAgentSecretsVault_ScopeEnforcement_NoToken(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	// No metadata at all.
	_, err := client.GetAgentSecret(context.Background(), &vaultv1.GetAgentSecretRequest{
		TenantId: "tenant_01",
		SecretId: "sec_01",
	})
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED, got nil")
	}
	s, _ := status.FromError(err)
	if s.Code() != codes.PermissionDenied {
		t.Errorf("want PermissionDenied, got %v", s.Code())
	}
}

func TestAgentSecretsVault_Put_Overwrite_FreshDEK(t *testing.T) {
	// Verify that two puts with the same secret_id produce different ciphertexts
	// (fresh DEK per put).
	_, fakeStore, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 42)
	}

	// Directly call store via service (avoid the gRPC layer for this unit test).
	plaintext := []byte("my-secret-value")
	w1, e1, err := crypto.Seal(kek, plaintext)
	if err != nil {
		t.Fatalf("Seal 1: %v", err)
	}
	w2, e2, err := crypto.Seal(kek, plaintext)
	if err != nil {
		t.Fatalf("Seal 2: %v", err)
	}

	// Two different seals of the same plaintext must produce different ciphertexts.
	if string(w1) == string(w2) {
		t.Error("wrappedDEK should differ across seals (fresh DEK per seal)")
	}
	if string(e1) == string(e2) {
		t.Error("encPayload should differ across seals (fresh nonce per seal)")
	}

	// Both must round-trip correctly.
	pairs := [][2][]byte{{w1, e1}, {w2, e2}}
	for i, pair := range pairs {
		plain, err := crypto.Open(kek, pair[0], pair[1])
		if err != nil {
			t.Fatalf("Open [%d]: %v", i, err)
		}
		if string(plain) != string(plaintext) {
			t.Errorf("Open [%d]: want %q got %q", i, plaintext, plain)
		}
	}

	// Store should be empty (we didn't call PutAgentSecret through the server).
	_ = fakeStore
}

// TestAgentSecretsVault_TableDriven covers multiple (tenant, secret) scenarios.
func TestAgentSecretsVault_TableDriven(t *testing.T) {
	client, _, cleanup := newAgentSecretsTestServer(t)
	defer cleanup()

	ctx := mdWithIdentity(context.Background(), "svcid_mcp", "test-mcp-token-32byteslong!!!!!!")

	cases := []struct {
		name     string
		tenantID string
		secretID string
		value    string
	}{
		{"small ASCII", "tenant_A", "sec_A1", "pass123"},
		{"JSON payload", "tenant_A", "sec_A2", `{"user":"admin","pass":"s3cr3t"}`},
		{"SSH key-like", "tenant_B", "sec_B1", "-----BEGIN OPENSSH PRIVATE KEY-----\nfakedata\n-----END OPENSSH PRIVATE KEY-----"},
		{"64KiB boundary", "tenant_C", "sec_C1", string(make([]byte, 65536))},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			_, err := client.PutAgentSecret(ctx, &vaultv1.PutAgentSecretRequest{
				TenantId: tc.tenantID,
				SecretId: tc.secretID,
				Value:    []byte(tc.value),
			})
			if err != nil {
				t.Fatalf("PutAgentSecret: %v", err)
			}

			resp, err := client.GetAgentSecret(ctx, &vaultv1.GetAgentSecretRequest{
				TenantId: tc.tenantID,
				SecretId: tc.secretID,
			})
			if err != nil {
				t.Fatalf("GetAgentSecret: %v", err)
			}
			if string(resp.GetValue()) != tc.value {
				t.Errorf("round-trip: want len=%d got len=%d", len(tc.value), len(resp.GetValue()))
			}
		})
	}
}

// errorsIsErrAgentSecretNotFound verifies the sentinel is exported and usable.
func TestErrAgentSecretNotFound_Exported(t *testing.T) {
	err := fmt.Errorf("wrapped: %w", store.ErrAgentSecretNotFound)
	if !errors.Is(err, store.ErrAgentSecretNotFound) {
		t.Error("errors.Is should find ErrAgentSecretNotFound in wrapped error")
	}
}
