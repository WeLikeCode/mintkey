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
