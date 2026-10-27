// Package vault — call timeout tests for the Vault Adapter gRPC client.
//
// Requirement: a Vault Adapter that accepts the call but never answers makes
// GetCredential fail at callTimeout, and callTimeout stays below Kong's
// upstream read timeout so the proxy answers 502 before Kong retries.
//
// Source: tests/acceptance/test_data_plane_resilience.py::test_vault_down_returns_502_no_cred_leak.
package vault

import (
	"context"
	"net"
	"testing"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// kongDefaultReadTimeout is Kong's default upstream read_timeout. kong-syncer
// creates the proxy-plugin services without overriding it.
const kongDefaultReadTimeout = 60 * time.Second

// hungVaultServer accepts GetCredential calls and never answers them.
type hungVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	release chan struct{}
}

func (s *hungVaultServer) GetCredential(ctx context.Context, _ *vaultv1.GetCredentialRequest) (*vaultv1.GetCredentialResponse, error) {
	select {
	case <-s.release:
	case <-ctx.Done():
	}
	return nil, status.Error(codes.Unavailable, "released")
}

func TestCallTimeoutBelowKongReadTimeout(t *testing.T) {
	if callTimeout >= kongDefaultReadTimeout {
		t.Fatalf("callTimeout = %s, want below Kong's read_timeout %s: Kong would retry the request before the proxy answers 502",
			callTimeout, kongDefaultReadTimeout)
	}
}

func TestGetCredentialHungAdapterFailsAtCallTimeout(t *testing.T) {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("net.Listen: %v", err)
	}
	srv := grpc.NewServer()
	hung := &hungVaultServer{release: make(chan struct{})}
	vaultv1.RegisterVaultAdapterServer(srv, hung)
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(func() {
		close(hung.release)
		srv.Stop()
	})

	saved := callTimeout
	callTimeout = 300 * time.Millisecond
	t.Cleanup(func() { callTimeout = saved })

	client := NewClient(lis.Addr().String(), "test-token", "svcid_test")
	t.Cleanup(func() { _ = client.Close() })

	start := time.Now()
	_, err = client.GetCredential(context.Background(), GetCredentialRequest{TenantID: "t", ServiceID: "s"})
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("GetCredential against a hung adapter returned no error")
	}
	if got := status.Code(err); got != codes.DeadlineExceeded {
		t.Fatalf("GetCredential error code = %s (%v), want DeadlineExceeded", got, err)
	}
	if elapsed < callTimeout || elapsed > callTimeout+2*time.Second {
		t.Fatalf("GetCredential returned after %s, want about callTimeout (%s)", elapsed, callTimeout)
	}
}
