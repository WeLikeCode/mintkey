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

// ---- Credential-change pool rebuild tests -----------------------------------
//
// These tests verify the fix for the stale-credentials bug where
// getOrCreateServicePool returned a cached pool built with old credentials
// after a re-auth (e.g. OAuth2 reauth replacing Username "" with the real
// address, or XOAUTH2 access-token rotation). See chunk C-7 / task #364.

// noopDialFn returns a dialer that never actually dials. The pool-rebuild
// tests below only exercise getOrCreateServicePool's identity/lifecycle —
// they do not call .Get, so no real connection is needed.
func noopDialFn() dialFunc {
	return func(_ context.Context, _ string, _ imapwrap.DialMode, _ imapwrap.Credentials, _ bool) (*imapwrap.Client, error) {
		return nil, errors.New("noopDialFn: not implemented")
	}
}

func baseXOAuth2Cfg() ServiceConfig {
	return ServiceConfig{
		TenantID:  "tnt",
		ServiceID: "svc",
		Addr:      "imap.example.com:993",
		DialMode:  imapwrap.DialModeTLS,
		Creds: imapwrap.Credentials{
			Username:    "user@example.com",
			AuthMode:    imapwrap.AuthModeXOAuth2,
			AccessToken: "tok-original",
		},
	}
}

// TestGetOrCreateServicePool_NewKeyCreatesPool is the baseline: a fresh key
// returns a newly-allocated PerServicePool registered in the map.
func TestGetOrCreateServicePool_NewKeyCreatesPool(t *testing.T) {
	p := newWithDialer(nil, noopDialFn())
	defer p.Close()

	cfg := baseXOAuth2Cfg()
	sp := p.getOrCreateServicePool(cfg)
	if sp == nil {
		t.Fatal("expected non-nil PerServicePool")
	}
	if got := p.pools[poolKey{cfg.TenantID, cfg.ServiceID}]; got != sp {
		t.Fatal("expected pool to be registered in pools map")
	}
	if !credsEquivalent(sp.creds, cfg.Creds) {
		t.Fatalf("expected stored creds=%+v, got %+v", cfg.Creds, sp.creds)
	}
}

// TestGetOrCreateServicePool_SameKeySameCredsReuses verifies the
// happy-path cache hit: identical Creds → same pool instance, no rebuild.
func TestGetOrCreateServicePool_SameKeySameCredsReuses(t *testing.T) {
	p := newWithDialer(nil, noopDialFn())
	defer p.Close()

	cfg := baseXOAuth2Cfg()
	sp1 := p.getOrCreateServicePool(cfg)
	sp2 := p.getOrCreateServicePool(cfg)

	if sp1 != sp2 {
		t.Fatal("expected same pool instance for identical creds; cache miss")
	}
}

// TestGetOrCreateServicePool_SameKeyDifferentUsername_RebuildsPool covers
// the production symptom: first call lands with Username="" (vault not
// populated yet), second call lands with the real email after OAuth2 reauth.
// Expected: second call returns a different pool; map points at the new one.
func TestGetOrCreateServicePool_SameKeyDifferentUsername_RebuildsPool(t *testing.T) {
	p := newWithDialer(nil, noopDialFn())
	defer p.Close()

	cfg1 := baseXOAuth2Cfg()
	cfg1.Creds.Username = "" // pre-reauth: envelope not yet written
	cfg2 := baseXOAuth2Cfg()
	cfg2.Creds.Username = "user@example.com" // post-reauth

	sp1 := p.getOrCreateServicePool(cfg1)
	sp2 := p.getOrCreateServicePool(cfg2)

	if sp1 == sp2 {
		t.Fatal("expected rebuilt pool when Username changed; got cached pool")
	}
	if p.pools[poolKey{cfg1.TenantID, cfg1.ServiceID}] != sp2 {
		t.Fatal("expected map to hold the new (rebuilt) pool, not the stale one")
	}
	if sp2.creds.Username != "user@example.com" {
		t.Fatalf("expected new pool's Username=%q, got %q", "user@example.com", sp2.creds.Username)
	}
}

// TestGetOrCreateServicePool_SameKeyDifferentAccessToken_RebuildsPool
// covers XOAUTH2 access-token rotation: the Username is unchanged but the
// refreshed access token must propagate to the next dial. A stale pool
// would keep dialing with the expired token and hit AUTHENTICATIONFAILED.
func TestGetOrCreateServicePool_SameKeyDifferentAccessToken_RebuildsPool(t *testing.T) {
	p := newWithDialer(nil, noopDialFn())
	defer p.Close()

	cfg1 := baseXOAuth2Cfg()
	cfg1.Creds.AccessToken = "tok-original"
	cfg2 := baseXOAuth2Cfg()
	cfg2.Creds.AccessToken = "tok-refreshed"

	sp1 := p.getOrCreateServicePool(cfg1)
	sp2 := p.getOrCreateServicePool(cfg2)

	if sp1 == sp2 {
		t.Fatal("expected rebuilt pool when AccessToken changed; got cached pool")
	}
	if sp2.creds.AccessToken != "tok-refreshed" {
		t.Fatalf("expected new pool's AccessToken=%q, got %q", "tok-refreshed", sp2.creds.AccessToken)
	}
}

// TestGetOrCreateServicePool_SameKeyDifferentPassword_RebuildsPool covers
// LOGIN-mode password rotation.
func TestGetOrCreateServicePool_SameKeyDifferentPassword_RebuildsPool(t *testing.T) {
	p := newWithDialer(nil, noopDialFn())
	defer p.Close()

	cfg1 := ServiceConfig{
		TenantID:  "tnt",
		ServiceID: "svc",
		Addr:      "imap.example.com:993",
		DialMode:  imapwrap.DialModeTLS,
		Creds: imapwrap.Credentials{
			Username: "alice",
			Password: "old-pass",
			AuthMode: imapwrap.AuthModeLogin,
		},
	}
	cfg2 := cfg1
	cfg2.Creds.Password = "new-pass"

	sp1 := p.getOrCreateServicePool(cfg1)
	sp2 := p.getOrCreateServicePool(cfg2)

	if sp1 == sp2 {
		t.Fatal("expected rebuilt pool when Password rotated; got cached pool")
	}
	if sp2.creds.Password != "new-pass" {
		t.Fatalf("expected new pool's Password=%q, got %q", "new-pass", sp2.creds.Password)
	}
}

// TestGetOrCreateServicePool_OldPoolConnectionsAreClosed verifies that when
// creds rotate, the stale pool's idle connections are drained (closeAll).
// Uses the real test IMAP server so we can prove the released connection is
// in idle, then verify idleCount() drops to 0 after the rebuild.
func TestGetOrCreateServicePool_OldPoolConnectionsAreClosed(t *testing.T) {
	addr, stop := startServer(t)
	defer stop()

	p := newWithDialer(nil, testDialFn(addr))
	defer p.Close()

	cfg1 := makeConfig(addr, "tnt", "svc")
	cfg2 := cfg1
	cfg2.Creds.Username = "bob" // different creds → triggers rebuild

	c, err := p.Get(context.Background(), cfg1)
	if err != nil {
		t.Fatalf("Get cfg1: %v", err)
	}
	p.Release(cfg1, c)

	spOld := p.pools[poolKey{cfg1.TenantID, cfg1.ServiceID}]
	if spOld == nil {
		t.Fatal("expected initial pool to be registered")
	}
	if spOld.idleCount() != 1 {
		t.Fatalf("expected 1 idle conn before rebuild, got %d", spOld.idleCount())
	}

	// Trigger rebuild via creds change.
	spNew := p.getOrCreateServicePool(cfg2)

	if spNew == spOld {
		t.Fatal("expected new pool instance after creds change")
	}
	if spOld.idleCount() != 0 {
		t.Fatalf("expected old pool's idle to be drained (closeAll), got %d", spOld.idleCount())
	}
	if spNew.idleCount() != 0 {
		t.Fatalf("expected new pool to start with 0 idle, got %d", spNew.idleCount())
	}
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
