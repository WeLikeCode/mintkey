// Package server — unit tests for the SSHVaultAdapter gRPC handlers.
//
// These tests use an in-process gRPC server (bufconn) backed by a fake
// SSHStore. They exercise:
//   - GetAgentByFingerprint: happy path, not-found, missing scope.
//   - GetHostKeyFingerprint: happy path (stored), empty (TOFU first-use).
//   - StoreHostKeyFingerprint: happy path, argument validation.
//
// Source: ADR-0021; chunk C7.
package server

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/sshvault"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

const sshBufSize = 1024 * 1024

// fakeSSHStore is an in-memory SSHStore for testing.
type fakeSSHStore struct {
	agents    map[string]*store.AgentSSHRecord   // fingerprint → record
	hostKeys  map[string]string                  // "tenantID/serviceID" → fingerprint
	storeErr  error                              // if set, returned by StoreHostKeyFingerprint
}

func (f *fakeSSHStore) GetAgentBySSHPubKey(_ context.Context, _, fp string) (*store.AgentSSHRecord, error) {
	return f.GetAgentBySSHPubKeyGlobal(context.Background(), fp)
}

func (f *fakeSSHStore) GetAgentBySSHPubKeyGlobal(_ context.Context, fp string) (*store.AgentSSHRecord, error) {
	r, ok := f.agents[fp]
	if !ok {
		return nil, store.ErrAgentNotFound
	}
	return r, nil
}

func (f *fakeSSHStore) GetHostKeyFingerprint(_ context.Context, tenantID, serviceID string) (string, error) {
	key := tenantID + "/" + serviceID
	return f.hostKeys[key], nil
}

func (f *fakeSSHStore) StoreHostKeyFingerprint(_ context.Context, tenantID, serviceID, fp string) error {
	if f.storeErr != nil {
		return f.storeErr
	}
	if f.hostKeys == nil {
		f.hostKeys = map[string]string{}
	}
	f.hostKeys[tenantID+"/"+serviceID] = fp
	return nil
}

// Ensure fakeSSHStore satisfies store.SSHStore.
var _ store.SSHStore = (*fakeSSHStore)(nil)

// newTestSSHGRPCServer spins up an SSHVaultAdapter gRPC server backed by the
// provided fakeSSHStore and a VaultService with a registered "ssh_proxy" identity.
// Returns a raw *grpc.ClientConn pointed at the server and a cleanup func.
func newTestSSHGRPCServer(t *testing.T, ss *fakeSSHStore) (*grpc.ClientConn, func()) {
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
	// Register a test service identity with both scopes.
	token := []byte("test-token-32-bytes-for-testing!!")
	if err := svc.RegisterServiceIdentity("svcid_ssh_proxy", token, []string{"vault.read", "vault.put"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	lis := bufconn.Listen(sshBufSize)
	grpcSrv := grpc.NewServer()
	RegisterSSHVaultServer(grpcSrv, svc, ss)
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
		_ = conn.Close()
		grpcSrv.Stop()
		_ = s.Close()
	}
	return conn, cleanup
}

// outCtx builds an outgoing context with the test service-identity headers.
func outCtx(ctx context.Context) context.Context {
	md := metadata.Pairs(
		"x-mintkey-service-identity", "svcid_ssh_proxy",
		"x-mintkey-service-token", "test-token-32-bytes-for-testing!!",
	)
	return metadata.NewOutgoingContext(ctx, md)
}

// --------------------------------------------------------------------------
// GetAgentByFingerprint tests
// --------------------------------------------------------------------------

func TestSSHVault_GetAgentByFingerprint_HappyPath(t *testing.T) {
	fs := &fakeSSHStore{
		agents: map[string]*store.AgentSSHRecord{
			"SHA256:abc123": {
				ID:        "agent_TEST",
				TenantID:  "tenant-uuid-1",
				Name:      "test agent",
				SSHPubKey: "ssh-ed25519 AAAA...",
				Status:    "active",
			},
		},
	}
	conn, cleanup := newTestSSHGRPCServer(t, fs)
	defer cleanup()

	ctx, cancel := context.WithTimeout(outCtx(context.Background()), 5*time.Second)
	defer cancel()

	req := &sshvault.GetAgentByFingerprintRequest{Fingerprint: "SHA256:abc123"}
	resp := &sshvault.GetAgentByFingerprintResponse{}

	err := conn.Invoke(
		ctx,
		"/mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint",
		req, resp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	)
	if err != nil {
		t.Fatalf("GetAgentByFingerprint: unexpected error: %v", err)
	}
	if resp.AgentID != "agent_TEST" {
		t.Errorf("AgentID: want agent_TEST, got %q", resp.AgentID)
	}
	if resp.TenantID != "tenant-uuid-1" {
		t.Errorf("TenantID: want tenant-uuid-1, got %q", resp.TenantID)
	}
	if resp.Status != "active" {
		t.Errorf("Status: want active, got %q", resp.Status)
	}
}

func TestSSHVault_GetAgentByFingerprint_NotFound(t *testing.T) {
	fs := &fakeSSHStore{agents: map[string]*store.AgentSSHRecord{}}
	conn, cleanup := newTestSSHGRPCServer(t, fs)
	defer cleanup()

	ctx, cancel := context.WithTimeout(outCtx(context.Background()), 5*time.Second)
	defer cancel()

	req := &sshvault.GetAgentByFingerprintRequest{Fingerprint: "SHA256:notfound"}
	resp := &sshvault.GetAgentByFingerprintResponse{}

	err := conn.Invoke(
		ctx,
		"/mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint",
		req, resp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	)
	if err == nil {
		t.Fatal("expected NOT_FOUND error, got nil")
	}
	st, ok := status.FromError(err)
	if !ok || st.Code() != codes.NotFound {
		t.Errorf("expected codes.NotFound, got %v", err)
	}
}

func TestSSHVault_GetAgentByFingerprint_MissingToken(t *testing.T) {
	fs := &fakeSSHStore{agents: map[string]*store.AgentSSHRecord{}}
	conn, cleanup := newTestSSHGRPCServer(t, fs)
	defer cleanup()

	// No service-identity metadata.
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	req := &sshvault.GetAgentByFingerprintRequest{Fingerprint: "SHA256:abc"}
	resp := &sshvault.GetAgentByFingerprintResponse{}

	err := conn.Invoke(
		ctx,
		"/mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint",
		req, resp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	)
	if err == nil {
		t.Fatal("expected PERMISSION_DENIED, got nil")
	}
	st, ok := status.FromError(err)
	if !ok || st.Code() != codes.PermissionDenied {
		t.Errorf("expected codes.PermissionDenied, got %v", err)
	}
}

// --------------------------------------------------------------------------
// GetHostKeyFingerprint tests
// --------------------------------------------------------------------------

func TestSSHVault_GetHostKeyFingerprint_HappyPath(t *testing.T) {
	fs := &fakeSSHStore{
		hostKeys: map[string]string{
			"tenant1/svc1": "SHA256:storedfingerprint",
		},
	}
	conn, cleanup := newTestSSHGRPCServer(t, fs)
	defer cleanup()

	ctx, cancel := context.WithTimeout(outCtx(context.Background()), 5*time.Second)
	defer cancel()

	req := &sshvault.HostKeyFingerprintRequest{TenantID: "tenant1", ServiceID: "svc1"}
	resp := &sshvault.HostKeyFingerprintResponse{}

	if err := conn.Invoke(
		ctx,
		"/mintkey.vault.v1.SSHVaultAdapter/GetHostKeyFingerprint",
		req, resp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	); err != nil {
		t.Fatalf("GetHostKeyFingerprint: %v", err)
	}
	if resp.Fingerprint != "SHA256:storedfingerprint" {
		t.Errorf("Fingerprint: want SHA256:storedfingerprint, got %q", resp.Fingerprint)
	}
}

func TestSSHVault_GetHostKeyFingerprint_TOFUFirstUse(t *testing.T) {
	fs := &fakeSSHStore{hostKeys: map[string]string{}}
	conn, cleanup := newTestSSHGRPCServer(t, fs)
	defer cleanup()

	ctx, cancel := context.WithTimeout(outCtx(context.Background()), 5*time.Second)
	defer cancel()

	req := &sshvault.HostKeyFingerprintRequest{TenantID: "tenant1", ServiceID: "svc-new"}
	resp := &sshvault.HostKeyFingerprintResponse{}

	if err := conn.Invoke(
		ctx,
		"/mintkey.vault.v1.SSHVaultAdapter/GetHostKeyFingerprint",
		req, resp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	); err != nil {
		t.Fatalf("GetHostKeyFingerprint (TOFU): %v", err)
	}
	if resp.Fingerprint != "" {
		t.Errorf("expected empty fingerprint for TOFU first-use, got %q", resp.Fingerprint)
	}
}

// --------------------------------------------------------------------------
// StoreHostKeyFingerprint tests
// --------------------------------------------------------------------------

func TestSSHVault_StoreHostKeyFingerprint_HappyPath(t *testing.T) {
	fs := &fakeSSHStore{hostKeys: map[string]string{}}
	conn, cleanup := newTestSSHGRPCServer(t, fs)
	defer cleanup()

	ctx, cancel := context.WithTimeout(outCtx(context.Background()), 5*time.Second)
	defer cancel()

	req := &sshvault.StoreHostKeyFingerprintRequest{
		TenantID:    "tenant1",
		ServiceID:   "svc1",
		Fingerprint: "SHA256:newhostkey",
	}
	resp := &sshvault.StoreHostKeyFingerprintResponse{}

	if err := conn.Invoke(
		ctx,
		"/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint",
		req, resp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	); err != nil {
		t.Fatalf("StoreHostKeyFingerprint: %v", err)
	}

	// Verify the value was stored.
	if fp := fs.hostKeys["tenant1/svc1"]; fp != "SHA256:newhostkey" {
		t.Errorf("stored fingerprint: want SHA256:newhostkey, got %q", fp)
	}
}

func TestSSHVault_StoreHostKeyFingerprint_MissingArgs(t *testing.T) {
	fs := &fakeSSHStore{hostKeys: map[string]string{}}
	conn, cleanup := newTestSSHGRPCServer(t, fs)
	defer cleanup()

	ctx, cancel := context.WithTimeout(outCtx(context.Background()), 5*time.Second)
	defer cancel()

	req := &sshvault.StoreHostKeyFingerprintRequest{
		TenantID:    "tenant1",
		ServiceID:   "",   // Missing
		Fingerprint: "SHA256:fp",
	}
	resp := &sshvault.StoreHostKeyFingerprintResponse{}

	err := conn.Invoke(
		ctx,
		"/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint",
		req, resp,
		grpc.ForceCodec(sshvault.JSONCodec{}),
	)
	if err == nil {
		t.Fatal("expected INVALID_ARGUMENT, got nil")
	}
	st, ok := status.FromError(err)
	if !ok || st.Code() != codes.InvalidArgument {
		t.Errorf("expected codes.InvalidArgument, got %v", err)
	}
}
