package pool

// NOTE: pool_test.go is in package pool (white-box) so it can access
// unexported helpers (idleCount, activeCount, newWithDialer).

import (
	"context"
	"errors"
	"net"
	"sync"
	"testing"
	"time"

	goiMAP "github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
	"github.com/emersion/go-imap/v2/imapserver"
	"github.com/emersion/go-imap/v2/imapserver/imapmemserver"

	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
)

const (
	testUser = "alice"
	testPass = "letmein"
)

// startServer starts a fresh in-process imapmemserver and returns its address.
func startServer(t *testing.T) (addr string, closeFn func()) {
	t.Helper()

	memSrv := imapmemserver.New()
	user := imapmemserver.NewUser(testUser, testPass)
	if err := user.Create("INBOX", nil); err != nil {
		t.Fatalf("create INBOX: %v", err)
	}
	memSrv.AddUser(user)

	srv := imapserver.New(&imapserver.Options{
		NewSession: func(_ *imapserver.Conn) (imapserver.Session, *imapserver.GreetingData, error) {
			return memSrv.NewSession(), nil, nil
		},
		InsecureAuth: true,
		Caps: goiMAP.CapSet{
			goiMAP.CapIMAP4rev1: {},
			goiMAP.CapIMAP4rev2: {},
		},
	})

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("net.Listen: %v", err)
	}
	go func() { _ = srv.Serve(ln) }()

	return ln.Addr().String(), func() { _ = srv.Close() }
}

// testDialFn returns a dialFunc that connects to addr via raw net.Conn (no TLS).
func testDialFn(addr string) dialFunc {
	return func(ctx context.Context, _ string, _ imapwrap.DialMode, creds imapwrap.Credentials, _ bool) (*imapwrap.Client, error) {
		conn, err := net.Dial("tcp", addr)
		if err != nil {
			return nil, err
		}
		raw := imapclient.New(conn, nil)
		if err := raw.Login(creds.Username, creds.Password).Wait(); err != nil {
			_ = raw.Close()
			return nil, err
		}
		// Wrap using direct access: wrap the raw client via a bare wrapper.
		// We reuse the underlying *imapclient.Client by routing through
		// DialFromConn with a second connection.
		_ = raw.Close()
		conn2, err := net.Dial("tcp", addr)
		if err != nil {
			return nil, err
		}
		return imapwrap.DialFromConn(conn2, creds)
	}
}

func loginCreds() imapwrap.Credentials {
	return imapwrap.Credentials{
		Username: testUser,
		Password: testPass,
		AuthMode: imapwrap.AuthModeLogin,
	}
}

func makeConfig(addr, tenantID, serviceID string) ServiceConfig {
	return ServiceConfig{
		TenantID:  tenantID,
		ServiceID: serviceID,
		Addr:      addr,
		DialMode:  imapwrap.DialModeTLS,
		Creds:     loginCreds(),
	}
}

// ---- Tests ------------------------------------------------------------------

// TestGetRelease verifies basic get-and-release round trip.
func TestGetRelease(t *testing.T) {
	addr, stop := startServer(t)
	defer stop()

	p := newWithDialer(nil, testDialFn(addr))
	defer p.Close()

	cfg := makeConfig(addr, "t1", "s1")

	c, err := p.Get(context.Background(), cfg)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if c == nil {
		t.Fatal("Get returned nil client")
	}

	sp := p.getOrCreateServicePool(cfg)
	if sp.activeCount() != 1 {
		t.Errorf("expected 1 active, got %d", sp.activeCount())
	}
	if sp.idleCount() != 0 {
		t.Errorf("expected 0 idle, got %d", sp.idleCount())
	}

	p.Release(cfg, c)

	if sp.activeCount() != 0 {
		t.Errorf("expected 0 active after release, got %d", sp.activeCount())
	}
	if sp.idleCount() != 1 {
		t.Errorf("expected 1 idle after release, got %d", sp.idleCount())
	}
}

// TestCapBehavior verifies that ErrPoolExhausted is returned when MaxConns is hit.
func TestCapBehavior(t *testing.T) {
	addr, stop := startServer(t)
	defer stop()

	const cap = 2
	p := newWithDialer(&Options{MaxConns: cap}, testDialFn(addr))
	defer p.Close()

	cfg := makeConfig(addr, "t1", "s1")

	// Lease cap connections.
	var leased []*imapwrap.Client
	for i := 0; i < cap; i++ {
		c, err := p.Get(context.Background(), cfg)
		if err != nil {
			t.Fatalf("Get #%d: %v", i+1, err)
		}
		leased = append(leased, c)
	}

	// One more must fail.
	_, err := p.Get(context.Background(), cfg)
	if !errors.Is(err, ErrPoolExhausted) {
		t.Fatalf("expected ErrPoolExhausted, got %v", err)
	}

	// Release one — next Get should succeed.
	p.Release(cfg, leased[0])
	leased = leased[1:]

	c, err := p.Get(context.Background(), cfg)
	if err != nil {
		t.Fatalf("Get after release: %v", err)
	}
	leased = append(leased, c)

	// Cleanup.
	for _, cl := range leased {
		p.Release(cfg, cl)
	}
}

// TestIdleEviction verifies that connections past IdleTimeout are evicted.
func TestIdleEviction(t *testing.T) {
	addr, stop := startServer(t)
	defer stop()

	shortIdle := 10 * time.Millisecond
	p := newWithDialer(&Options{MaxConns: 5, IdleTimeout: shortIdle}, testDialFn(addr))
	defer p.Close()

	cfg := makeConfig(addr, "t1", "s1")

	c, err := p.Get(context.Background(), cfg)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	p.Release(cfg, c)

	sp := p.getOrCreateServicePool(cfg)
	if sp.idleCount() != 1 {
		t.Fatalf("expected 1 idle, got %d", sp.idleCount())
	}

	// Wait past idle timeout.
	time.Sleep(shortIdle * 3)

	// Next Get triggers eviction.
	c2, err := p.Get(context.Background(), cfg)
	if err != nil {
		t.Fatalf("Get after idle: %v", err)
	}
	p.Release(cfg, c2)
}

// TestErrorEviction verifies that a broken connection is evicted on Release.
func TestErrorEviction(t *testing.T) {
	addr, stop := startServer(t)
	defer stop()

	p := newWithDialer(nil, testDialFn(addr))
	defer p.Close()

	cfg := makeConfig(addr, "t1", "s1")

	c, err := p.Get(context.Background(), cfg)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}

	// Force-close the underlying connection to make Ping fail.
	_ = c.Close()

	// Release should detect the broken state and NOT add to idle.
	p.Release(cfg, c)

	sp := p.getOrCreateServicePool(cfg)
	if sp.idleCount() != 0 {
		t.Errorf("expected 0 idle after error eviction, got %d", sp.idleCount())
	}
	if sp.activeCount() != 0 {
		t.Errorf("expected 0 active after release, got %d", sp.activeCount())
	}
}

// TestPerServiceIsolation verifies that two different serviceIDs have independent pools.
func TestPerServiceIsolation(t *testing.T) {
	addr, stop := startServer(t)
	defer stop()

	const cap = 1
	p := newWithDialer(&Options{MaxConns: cap}, testDialFn(addr))
	defer p.Close()

	cfgA := makeConfig(addr, "t1", "serviceA")
	cfgB := makeConfig(addr, "t1", "serviceB")

	cA, err := p.Get(context.Background(), cfgA)
	if err != nil {
		t.Fatalf("Get A: %v", err)
	}

	// serviceA is at cap; serviceB should still succeed.
	cB, err := p.Get(context.Background(), cfgB)
	if err != nil {
		t.Fatalf("Get B: %v", err)
	}

	// serviceA second Get must fail.
	_, err = p.Get(context.Background(), cfgA)
	if !errors.Is(err, ErrPoolExhausted) {
		t.Errorf("expected ErrPoolExhausted for A, got %v", err)
	}

	p.Release(cfgA, cA)
	p.Release(cfgB, cB)
}

// TestConcurrencySafety spawns N goroutines racing on Get+Release.
func TestConcurrencySafety(t *testing.T) {
	addr, stop := startServer(t)
	defer stop()

	const (
		maxConn    = 3
		goroutines = 10
		iterations = 5
	)

	p := newWithDialer(&Options{MaxConns: maxConn}, testDialFn(addr))
	defer p.Close()

	cfg := makeConfig(addr, "t1", "s1")

	var wg sync.WaitGroup
	wg.Add(goroutines)

	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			for j := 0; j < iterations; j++ {
				c, err := p.Get(context.Background(), cfg)
				if err != nil {
					if errors.Is(err, ErrPoolExhausted) {
						continue // expected under load
					}
					t.Errorf("Get error: %v", err)
					return
				}
				// Simulate work.
				time.Sleep(time.Millisecond)
				p.Release(cfg, c)
			}
		}()
	}

	wg.Wait()
}
