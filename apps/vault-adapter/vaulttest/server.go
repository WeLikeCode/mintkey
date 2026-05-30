// Package vaulttest provides a test-only in-process vault-adapter gRPC server
// for cross-module integration testing.
//
// This package is non-internal so proxy-plugin tests can import it via the
// go.work workspace.  It MUST NOT be imported by production code.
//
// Source: remediation/active/2026-05-28-service-templates-adversarial/
//         00-findings-and-intake.md BUG-1 (FAIL-2 cross-module test requirement).
package vaulttest

import (
	"context"
	"fmt"
	"net"
	"time"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/server"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
)

// Server is a test vault-adapter gRPC server running on a real TCP port.
// It uses the PRODUCTION VaultServer.ListenAndServe code path including the
// real scopeInterceptor — the same code that runs in docker-compose.
type Server struct {
	Addr   string         // "127.0.0.1:<port>"
	cancel context.CancelFunc
}

// Start starts a vault-adapter gRPC server with the given shared proxy secret.
// identityID and token must match the values the proxy client will present.
// scopes are the permissions granted to that identity.
//
// The returned Server.Addr is a "127.0.0.1:<port>" address suitable for
// vault.NewClient(addr, token, identityID).
//
// Stop must be called to release the listener.
func Start(identityID string, token []byte, scopes []string) (*Server, error) {
	// Pick a random free port.
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, fmt.Errorf("vaulttest.Start: listen: %w", err)
	}
	port := lis.Addr().(*net.TCPAddr).Port
	lis.Close()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}

	st, err := store.New(":memory:")
	if err != nil {
		return nil, fmt.Errorf("vaulttest.Start: store: %w", err)
	}

	svc := server.NewVaultService(kek, st)
	if err := svc.RegisterServiceIdentity(identityID, token, scopes); err != nil {
		_ = st.Close()
		return nil, fmt.Errorf("vaulttest.Start: RegisterServiceIdentity: %w", err)
	}

	srv := server.New(kek)
	ctx, cancel := context.WithCancel(context.Background())

	errCh := make(chan error, 1)
	go func() {
		errCh <- srv.ListenAndServe(ctx, port, svc)
	}()

	// Wait up to 2s for the port to be available.
	addr := fmt.Sprintf("127.0.0.1:%d", port)
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		c, err := net.DialTimeout("tcp", addr, 100*time.Millisecond)
		if err == nil {
			c.Close()
			return &Server{Addr: addr, cancel: cancel}, nil
		}
		// Check for startup error.
		select {
		case err := <-errCh:
			cancel()
			_ = st.Close()
			return nil, fmt.Errorf("vaulttest.Start: server error: %w", err)
		default:
		}
		time.Sleep(20 * time.Millisecond)
	}

	cancel()
	_ = st.Close()
	return nil, fmt.Errorf("vaulttest.Start: server did not become ready on %s within 2s", addr)
}

// Stop shuts down the vault-adapter server.
func (s *Server) Stop() {
	if s.cancel != nil {
		s.cancel()
	}
}
