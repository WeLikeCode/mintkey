// Package vault_test — connection reuse tests for the Vault Adapter gRPC client.
//
// Requirement: the proxy reuses one connection to the vault; the client recovers
// after a vault restart and refuses to connect once it has been closed.
//
// Source: openspec/changes/vault-service-identity-fast-check (task 2.1).
package vault_test

import (
	"context"
	"fmt"
	"net"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

const (
	testServiceToken = "conn-test-token"
	testServiceID    = "svcid_conn_test"
)

// countingListener counts successful Accept calls so a test can assert how many
// TCP connections the client actually opened.
type countingListener struct {
	net.Listener
	accepts atomic.Int32
}

func (l *countingListener) Accept() (net.Conn, error) {
	conn, err := l.Listener.Accept()
	if err == nil {
		l.accepts.Add(1)
	}
	return conn, err
}

type recordedCall struct {
	identity string
	token    string
}

// recordingVaultServer records the identity metadata of every GetCredential
// call and returns a fixed credential value.
type recordingVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	mu    sync.Mutex
	calls []recordedCall
}

func (s *recordingVaultServer) GetCredential(ctx context.Context, _ *vaultv1.GetCredentialRequest) (*vaultv1.GetCredentialResponse, error) {
	md, _ := metadata.FromIncomingContext(ctx)
	call := recordedCall{
		identity: firstValue(md.Get("x-mintkey-service-identity")),
		token:    firstValue(md.Get("x-mintkey-service-token")),
	}

	s.mu.Lock()
	s.calls = append(s.calls, call)
	s.mu.Unlock()

	return &vaultv1.GetCredentialResponse{
		AuthScheme:         vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:              []byte("conn-test-value"),
		ReturnedKeyVersion: 1,
	}, nil
}

func (s *recordingVaultServer) recordedCalls() []recordedCall {
	s.mu.Lock()
	defer s.mu.Unlock()

	out := make([]recordedCall, len(s.calls))
	copy(out, s.calls)
	return out
}

func firstValue(values []string) string {
	if len(values) == 0 {
		return ""
	}
	return values[0]
}

func listenOn(t *testing.T, addr string) *countingListener {
	t.Helper()

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		t.Fatalf("net.Listen(%q): %v", addr, err)
	}
	return &countingListener{Listener: lis}
}

func listenOnAfterRestart(t *testing.T, addr string) *countingListener {
	t.Helper()

	deadline := time.Now().Add(2 * time.Second)
	var lastErr error
	for {
		lis, err := net.Listen("tcp", addr)
		if err == nil {
			return &countingListener{Listener: lis}
		}
		lastErr = err
		if time.Now().After(deadline) {
			t.Fatalf("net.Listen(%q) after restart: %v", addr, lastErr)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func serveVault(t *testing.T, lis net.Listener) (*grpc.Server, *recordingVaultServer) {
	t.Helper()

	srv := grpc.NewServer()
	fake := &recordingVaultServer{}
	vaultv1.RegisterVaultAdapterServer(srv, fake)

	go func() {
		_ = srv.Serve(lis)
	}()
	t.Cleanup(srv.Stop)

	return srv, fake
}

func newTestServer(t *testing.T) (string, *countingListener, *grpc.Server, *recordingVaultServer) {
	t.Helper()

	lis := listenOn(t, "127.0.0.1:0")
	srv, fake := serveVault(t, lis)
	return lis.Addr().String(), lis, srv, fake
}

func TestClient_SequentialCallsShareOneConnection_C_2dee6bf7(t *testing.T) {
	addr, lis, _, fake := newTestServer(t)
	client := vault.NewClient(addr, testServiceToken, testServiceID)

	for i := 0; i < 5; i++ {
		resp, err := client.GetCredential(context.Background(), vault.GetCredentialRequest{
			TenantID:  "tenant_conn",
			ServiceID: "svc_conn",
		})
		if err != nil {
			t.Fatalf("GetCredential call %d: %v", i, err)
		}
		if string(resp.Plaintext) != "conn-test-value" {
			t.Fatalf("GetCredential call %d returned %q, want %q", i, resp.Plaintext, "conn-test-value")
		}
	}

	if got := lis.accepts.Load(); got != 1 {
		t.Fatalf("listener accepted %d connections for 5 sequential calls, want 1", got)
	}

	calls := fake.recordedCalls()
	if len(calls) != 5 {
		t.Fatalf("server saw %d GetCredential calls, want 5", len(calls))
	}
	for i, call := range calls {
		if call.identity != testServiceID {
			t.Errorf("call %d identity = %q, want %q", i, call.identity, testServiceID)
		}
		if call.token != testServiceToken {
			t.Errorf("call %d token = %q, want %q", i, call.token, testServiceToken)
		}
	}
}

func TestClient_ConcurrentCallsShareOneConnection_C_51e2f67d(t *testing.T) {
	addr, lis, _, _ := newTestServer(t)
	client := vault.NewClient(addr, testServiceToken, testServiceID)

	const callers = 16
	var wg sync.WaitGroup
	errs := make(chan error, callers)

	wg.Add(callers)
	for i := 0; i < callers; i++ {
		go func(n int) {
			defer wg.Done()

			resp, err := client.GetCredential(context.Background(), vault.GetCredentialRequest{
				TenantID:  "tenant_conn",
				ServiceID: "svc_conn",
			})
			if err != nil {
				errs <- fmt.Errorf("caller %d: %w", n, err)
				return
			}
			if string(resp.Plaintext) != "conn-test-value" {
				errs <- fmt.Errorf("caller %d returned %q, want %q", n, resp.Plaintext, "conn-test-value")
			}
		}(i)
	}
	wg.Wait()
	close(errs)

	for err := range errs {
		t.Error(err)
	}
	if t.Failed() {
		return
	}

	if got := lis.accepts.Load(); got != 1 {
		t.Fatalf("listener accepted %d connections for 16 concurrent calls, want 1", got)
	}
}

func TestClient_RecoversAfterVaultRestart_C_fdfe8e11_C_2dee6bf7(t *testing.T) {
	addr, _, srv, _ := newTestServer(t)
	client := vault.NewClient(addr, testServiceToken, testServiceID)

	if _, err := client.GetCredential(context.Background(), vault.GetCredentialRequest{
		TenantID:  "tenant_conn",
		ServiceID: "svc_conn",
	}); err != nil {
		t.Fatalf("initial GetCredential: %v", err)
	}

	srv.Stop()

	newLis := listenOnAfterRestart(t, addr)
	serveVault(t, newLis)

	deadline := time.Now().Add(10 * time.Second)
	var lastErr error
	recovered := false
	for time.Now().Before(deadline) {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		resp, err := client.GetCredential(ctx, vault.GetCredentialRequest{
			TenantID:  "tenant_conn",
			ServiceID: "svc_conn",
		})
		cancel()

		if err == nil && string(resp.Plaintext) == "conn-test-value" {
			recovered = true
			break
		}
		if err != nil {
			lastErr = err
		} else {
			lastErr = fmt.Errorf("response %q, want %q", resp.Plaintext, "conn-test-value")
		}
		time.Sleep(100 * time.Millisecond)
	}
	if !recovered {
		t.Fatalf("GetCredential did not recover within 10s of the vault restart: %v", lastErr)
	}

	// After recovery the client keeps its connection: one more call must not
	// make the restarted listener accept another connection.
	before := newLis.accepts.Load()
	if _, err := client.GetCredential(context.Background(), vault.GetCredentialRequest{
		TenantID:  "tenant_conn",
		ServiceID: "svc_conn",
	}); err != nil {
		t.Fatalf("GetCredential after recovery: %v", err)
	}
	if got := newLis.accepts.Load(); got != before {
		t.Fatalf("a call after recovery opened a new connection: accepted %d, was %d", got, before)
	}
}

func TestClient_ClosedClientDoesNotConnect_C_5933cf84(t *testing.T) {
	addr, lis, _, _ := newTestServer(t)
	client := vault.NewClient(addr, testServiceToken, testServiceID)

	if _, err := client.GetCredential(context.Background(), vault.GetCredentialRequest{
		TenantID:  "tenant_conn",
		ServiceID: "svc_conn",
	}); err != nil {
		t.Fatalf("GetCredential before Close: %v", err)
	}

	closer, ok := any(client).(interface{ Close() error })
	if !ok {
		t.Fatal("vault.Client does not implement Close() error")
	}
	if err := closer.Close(); err != nil {
		t.Fatalf("first Close: %v", err)
	}

	before := lis.accepts.Load()
	_, err := client.GetCredential(context.Background(), vault.GetCredentialRequest{
		TenantID:  "tenant_conn",
		ServiceID: "svc_conn",
	})
	if err == nil {
		t.Fatal("GetCredential after Close returned nil error")
	}
	if !strings.Contains(err.Error(), "vault: client closed") {
		t.Fatalf("GetCredential after Close error = %q, want it to contain %q", err, "vault: client closed")
	}
	if got := lis.accepts.Load(); got != before {
		t.Fatalf("GetCredential after Close opened a connection: accepted %d, was %d", got, before)
	}
	if err := closer.Close(); err != nil {
		t.Fatalf("second Close: %v", err)
	}
}
