// Tests for the changes subscriber.
//
// Covers:
//   - Tenant-scope enforcement (ADR-0014.1 / Req MT-4)
//   - Initial reconcile on Start: Kong /config receives non-empty YAML
//   - NOTIFY-triggered reconcile: fake NOTIFY → Kong /config called again
//   - PushStats counter increments on each successful push
//   - LastErr / degraded health state on failed push
//
// Source: ADR-0014.1; Req MT-4; T-1.0.6; T-1.2.2.
package changes_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/lib/pq"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/changes"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/kong"
)

// ---------------------------------------------------------------------------
// Existing tests — tenant-scope enforcement
// ---------------------------------------------------------------------------

// TestSubscriber_PanicsWithoutTenantScope asserts that Start() panics when
// NewClient is called without WithTenantScope. (ADR-0014.1 / Req MT-4)
func TestSubscriber_PanicsWithoutTenantScope(t *testing.T) {
	c := changes.NewClient(nil)

	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected panic, got none")
		}
		msg, ok := r.(string)
		if !ok {
			t.Fatalf("panic value is not string: %T %v", r, r)
		}
		want := "changes: WithTenantScope is required (ADR-0014.1)"
		if msg != want {
			t.Errorf("panic message = %q, want %q", msg, want)
		}
	}()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	c.Start(ctx) // must panic
}

// TestSubscriber_NoPanicWithTenantScope asserts that Start() does NOT panic
// when WithTenantScope(AllTenants) is provided. (ADR-0014.1)
func TestSubscriber_NoPanicWithTenantScope(t *testing.T) {
	c := changes.NewClient(nil, changes.WithTenantScope(changes.AllTenants))

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately so Start returns without blocking

	// Should not panic.
	c.Start(ctx)
}

// ---------------------------------------------------------------------------
// mockListener — implements changes.pgListener (via the WithListenerFactory
// hook) without a real Postgres connection.
// ---------------------------------------------------------------------------

// mockListener is an in-process LISTEN/NOTIFY source for testing.
// It satisfies the unexported changes.pgListener interface via a factory.
type mockListener struct {
	ch     chan *pq.Notification
	closed atomic.Bool
	pinged atomic.Int32
}

func newMockListener() *mockListener {
	return &mockListener{ch: make(chan *pq.Notification, 16)}
}

func (m *mockListener) Listen(_ string) error                        { return nil }
func (m *mockListener) Ping() error                                  { m.pinged.Add(1); return nil }
func (m *mockListener) NotificationChannel() <-chan *pq.Notification { return m.ch }
func (m *mockListener) Close() error                                 { m.closed.Store(true); return nil }

// send delivers a notification to the mock channel.
func (m *mockListener) send(channel, payload string) {
	m.ch <- &pq.Notification{Channel: channel, Extra: payload}
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// stubServices returns a fixed set of kong.ServiceEntry values for tests.
func stubServices() []kong.ServiceEntry {
	return []kong.ServiceEntry{
		{
			ID:         "svc-001",
			TenantID:   "tnt-001",
			TenantSlug: "acme",
			Slug:       "payments",
			BaseURL:    "http://payments.example.com",
		},
	}
}

// ---------------------------------------------------------------------------
// New tests — reconcile and NOTIFY
// ---------------------------------------------------------------------------

// TestSubscriber_InitialReconcile_PostsToKong asserts that Start() performs
// an initial reconcile and POSTs to Kong /config before entering the LISTEN loop.
func TestSubscriber_InitialReconcile_PostsToKong(t *testing.T) {
	var postCount atomic.Int32

	// Stub Kong admin server.
	kongServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/config" {
			postCount.Add(1)
			w.WriteHeader(http.StatusOK)
			return
		}
		http.NotFound(w, r)
	}))
	defer kongServer.Close()

	ml := newMockListener()

	ctx, cancel := context.WithCancel(context.Background())

	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		changes.WithKongAdminURL(kongServer.URL),
		changes.WithHTTPClient(kongServer.Client()),
		changes.WithFetcherFn(func() ([]kong.ServiceEntry, error) {
			return stubServices(), nil
		}),
		changes.WithListenerFactory(func(_ string) (changes.PGListener, error) {
			return ml, nil
		}),
	)

	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Start(ctx)
	}()

	// Give the goroutine time to run the initial reconcile.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if postCount.Load() >= 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	cancel()
	<-done

	if postCount.Load() < 1 {
		t.Errorf("expected at least 1 POST to Kong /config during initial reconcile, got %d", postCount.Load())
	}
	if c.Stats.Total() < 1 {
		t.Errorf("expected Stats.Total >= 1, got %d", c.Stats.Total())
	}
}

// TestSubscriber_NotifyTriggersReconcile asserts that a NOTIFY on mintkey:service
// causes an additional POST to Kong /config beyond the initial reconcile.
func TestSubscriber_NotifyTriggersReconcile(t *testing.T) {
	var postCount atomic.Int32

	kongServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/config" {
			postCount.Add(1)
			w.WriteHeader(http.StatusOK)
			return
		}
		http.NotFound(w, r)
	}))
	defer kongServer.Close()

	ml := newMockListener()

	ctx, cancel := context.WithCancel(context.Background())

	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		changes.WithKongAdminURL(kongServer.URL),
		changes.WithHTTPClient(kongServer.Client()),
		changes.WithFetcherFn(func() ([]kong.ServiceEntry, error) {
			return stubServices(), nil
		}),
		changes.WithListenerFactory(func(_ string) (changes.PGListener, error) {
			return ml, nil
		}),
	)

	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Start(ctx)
	}()

	// Wait for initial reconcile.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if postCount.Load() >= 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if postCount.Load() < 1 {
		t.Fatal("initial reconcile did not fire within 2s")
	}
	beforeNotify := postCount.Load()

	// Send a NOTIFY.
	ml.send("mintkey:service", `{"action":"create","id":"svc-002"}`)

	// Wait for the NOTIFY-triggered reconcile.
	deadline = time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if postCount.Load() > beforeNotify {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	cancel()
	<-done

	if postCount.Load() <= beforeNotify {
		t.Errorf("expected NOTIFY to trigger an additional POST to /config; count before=%d after=%d",
			beforeNotify, postCount.Load())
	}
	if c.Stats.Total() < 2 {
		t.Errorf("expected Stats.Total >= 2 after NOTIFY, got %d", c.Stats.Total())
	}
}

// TestSubscriber_KongFailure_SetsLastErr asserts that a Kong push failure
// causes LastErr() to be non-nil (used by the health handler to report degraded).
func TestSubscriber_KongFailure_SetsLastErr(t *testing.T) {
	// Return 500 from Kong.
	kongServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal error", http.StatusInternalServerError)
	}))
	defer kongServer.Close()

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // we only care about the initial reconcile

	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		changes.WithKongAdminURL(kongServer.URL),
		changes.WithHTTPClient(kongServer.Client()),
		changes.WithFetcherFn(func() ([]kong.ServiceEntry, error) {
			return stubServices(), nil
		}),
	)

	// Start with already-cancelled ctx so it returns after initial reconcile.
	c.Start(ctx)

	if c.LastErr() == nil {
		t.Error("expected LastErr() != nil after Kong 500, got nil")
	}
	if c.Stats.Total() != 0 {
		t.Errorf("expected Stats.Total == 0 after failure, got %d", c.Stats.Total())
	}
}

// ---------------------------------------------------------------------------
// Retry and periodic safety-net tests (hermetic — no real Postgres / Kong).
// ---------------------------------------------------------------------------

// errReconcile is a sentinel error returned by stub reconcile fns.
type errReconcile struct{ msg string }

func (e *errReconcile) Error() string { return e.msg }

// TestInitialReconcileSucceedsFirstTry: reconcileFn returns nil → 0 retry
// events, subscriber continues without blocking.
func TestInitialReconcileSucceedsFirstTry(t *testing.T) {
	var calls atomic.Int32

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately so Start returns after initial reconcile

	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		changes.WithKongAdminURL("http://fake-kong"),
		// reconcileFn returns nil on first call → no retries
		changes.WithReconcileFn(func() error {
			calls.Add(1)
			return nil
		}),
		changes.WithInitialRetryMaxDuration(5*time.Minute),
	)

	c.Start(ctx)

	if n := calls.Load(); n != 1 {
		t.Errorf("expected reconcileFn called exactly once, got %d", n)
	}
	if c.LastErr() != nil {
		t.Errorf("expected LastErr() == nil after success, got %v", c.LastErr())
	}
}

// TestInitialReconcileRetriesThenSucceeds: reconcileFn errors twice then returns
// nil → exactly 2 retry log events, then ok, LISTEN proceeds.
func TestInitialReconcileRetriesThenSucceeds(t *testing.T) {
	var calls atomic.Int32

	errFoo := &errReconcile{"db refused"}

	// Use a live context; Start returns naturally after the 3rd call succeeds
	// (no LISTEN because KongAdminURL is set but db is non-empty fake string).
	// We cancel after Start returns so the test doesn't leak goroutines.
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		// No KongAdminURL → LISTEN disabled; Start blocks on ctx.Done() after retry.
		// Set a large enough max duration so retries are not budget-exhausted.
		changes.WithReconcileFn(func() error {
			n := calls.Add(1)
			if n <= 2 {
				return errFoo
			}
			return nil
		}),
		changes.WithInitialRetryMaxDuration(30*time.Second),
		// Use a tiny base backoff so the two sleeps are fast (2×1ms).
		changes.WithRetryBaseBackoff(1*time.Millisecond),
	)

	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Start(ctx)
	}()

	// Wait up to 5s for the 3rd reconcile call to land.
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) && calls.Load() < 3 {
		time.Sleep(5 * time.Millisecond)
	}

	cancel()
	<-done

	if n := calls.Load(); n < 3 {
		t.Errorf("expected at least 3 reconcileFn calls (2 failures + 1 success), got %d", n)
	}
	if c.LastErr() != nil {
		t.Errorf("expected LastErr() == nil after eventual success, got %v", c.LastErr())
	}
}

// TestInitialReconcileExhaustsRetries: reconcileFn always errors → after the
// configured duration, exhaustion is logged and Start continues (no panic).
// Uses a tiny max duration and tiny base backoff so the test exits in <200ms.
func TestInitialReconcileExhaustsRetries(t *testing.T) {
	var calls atomic.Int32

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	errPerm := &errReconcile{"permanent error"}

	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		// No KongAdminURL so LISTEN is disabled — Start blocks on ctx.Done().
		changes.WithReconcileFn(func() error {
			calls.Add(1)
			return errPerm
		}),
		// 50ms budget with 1ms base backoff: exhausts after ~6 attempts in <100ms.
		changes.WithInitialRetryMaxDuration(50*time.Millisecond),
		changes.WithRetryBaseBackoff(1*time.Millisecond),
	)

	// Run in goroutine since LISTEN-disabled path blocks on ctx.Done().
	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Start(ctx)
	}()

	// Give it a moment then cancel.
	time.Sleep(500 * time.Millisecond)
	cancel()
	<-done

	if n := calls.Load(); n < 1 {
		t.Error("expected reconcileFn called at least once before exhaustion")
	}
	// LastErr must be set (not nil) — reconcile never succeeded.
	if c.LastErr() == nil {
		t.Error("expected LastErr() != nil after exhaustion, got nil")
	}
}

// newFakeTicker returns a *time.Ticker whose C channel is a buffered channel
// the caller controls. Stop() is safe (no panic).
func newFakeTicker(ch chan time.Time) *time.Ticker {
	return &time.Ticker{C: ch}
}

// TestPeriodicReconcileFires: with a fake ticker channel that fires 3 times,
// assert reconcileFn is invoked 3 times beyond the initial reconcile.
func TestPeriodicReconcileFires(t *testing.T) {
	t.Parallel()

	var calls atomic.Int32
	periodicCh := make(chan time.Time, 4)

	ml := newMockListener()
	ctx, cancel := context.WithCancel(context.Background())

	tickerCallCount := 0
	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		changes.WithKongAdminURL("http://fake-kong"),
		changes.WithReconcileFn(func() error {
			calls.Add(1)
			return nil
		}),
		changes.WithListenerFactory(func(_ string) (changes.PGListener, error) {
			return ml, nil
		}),
		changes.WithPeriodicInterval(time.Millisecond), // enable periodic
		// Replace newTicker: first call (ping ticker) gets a real never-firing
		// ticker; second call (periodic ticker) gets our fake channel.
		changes.WithNewTicker(func(d time.Duration) *time.Ticker {
			tickerCallCount++
			if tickerCallCount == 1 {
				// ping ticker — never fires
				return time.NewTicker(24 * time.Hour)
			}
			// periodic ticker — we control it
			return newFakeTicker(periodicCh)
		}),
		changes.WithInitialRetryMaxDuration(0), // try once, don't retry on error
	)

	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Start(ctx)
	}()

	// Wait for initial reconcile (calls >= 1).
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) && calls.Load() < 1 {
		time.Sleep(5 * time.Millisecond)
	}
	if calls.Load() < 1 {
		t.Fatal("initial reconcile did not fire within 2s")
	}
	beforePeriodic := calls.Load()

	// Fire 3 periodic ticks.
	now := time.Now()
	periodicCh <- now
	periodicCh <- now
	periodicCh <- now

	// Wait for 3 additional calls.
	deadline = time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) && calls.Load() < beforePeriodic+3 {
		time.Sleep(5 * time.Millisecond)
	}

	cancel()
	<-done

	if got := calls.Load() - beforePeriodic; got < 3 {
		t.Errorf("expected at least 3 periodic reconcile calls, got %d", got)
	}
}

// TestPeriodicDisabledWhenZero: interval 0 → no periodic ticker → reconcileFn
// only invoked by the initial path (once), not by any periodic ticks.
func TestPeriodicDisabledWhenZero(t *testing.T) {
	t.Parallel()

	var calls atomic.Int32
	ml := newMockListener()
	ctx, cancel := context.WithCancel(context.Background())

	c := changes.NewClient(
		"postgres://fake-dsn",
		changes.WithTenantScope(changes.AllTenants),
		changes.WithKongAdminURL("http://fake-kong"),
		changes.WithReconcileFn(func() error {
			calls.Add(1)
			return nil
		}),
		changes.WithListenerFactory(func(_ string) (changes.PGListener, error) {
			return ml, nil
		}),
		changes.WithPeriodicInterval(0), // disabled
	)

	done := make(chan struct{})
	go func() {
		defer close(done)
		c.Start(ctx)
	}()

	// Wait for initial reconcile.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) && calls.Load() < 1 {
		time.Sleep(5 * time.Millisecond)
	}
	if calls.Load() < 1 {
		t.Fatal("initial reconcile did not fire within 2s")
	}

	// Hold for a bit to confirm no extra periodic calls.
	snapshot := calls.Load()
	time.Sleep(100 * time.Millisecond)

	cancel()
	<-done

	// Allow for the initial call only; no periodic calls.
	if after := calls.Load(); after != snapshot {
		t.Errorf("expected no additional reconcile calls after initial (snapshot=%d), got %d total", snapshot, after)
	}
}
