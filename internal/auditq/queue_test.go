// Package auditq_test covers the async audit queue.
//
// Source: #22 async audit emission.
package auditq_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/internal/auditq"
)

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

func tmpWAL(t *testing.T) string {
	t.Helper()
	return filepath.Join(t.TempDir(), "test.wal")
}

// startQueue creates a Queue backed by srv, writes to walPath, and starts it.
func startQueue(t *testing.T, srv *httptest.Server, walPath string) *auditq.Queue {
	t.Helper()
	q := auditq.New(srv.URL, "test-token", walPath)
	q.Replay()
	q.Start()
	return q
}

func newEvent(typ string) auditq.Event {
	return auditq.Event{
		EventType:  typ,
		TenantID:   "tenant_01HXYZ",
		ActorType:  "agent",
		ActorID:    "agent_01HABC",
		TargetID:   "svc_01HDEF",
		TargetType: "service",
		Payload:    map[string]any{"test": true},
	}
}

// ---------------------------------------------------------------------------
// TestEnqueueDrainHappyPath
// ---------------------------------------------------------------------------

func TestEnqueueDrainHappyPath(t *testing.T) {
	var mu sync.Mutex
	var received []auditq.Event

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var e auditq.Event
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &e)
		mu.Lock()
		received = append(received, e)
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startQueue(t, srv, wal)

	q.Enqueue(newEvent("token.issued"))
	q.Enqueue(newEvent("proxy.hit"))

	// Wait for drain (up to 2s)
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(received)
		mu.Unlock()
		if n == 2 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	q.Close()

	mu.Lock()
	n := len(received)
	mu.Unlock()
	if n != 2 {
		t.Fatalf("expected 2 events delivered, got %d", n)
	}
}

// ---------------------------------------------------------------------------
// TestChannelFullWALPersist
// ---------------------------------------------------------------------------

// TestChannelFullWALPersist verifies that when the channel is full the event
// is still written to the WAL and can be replayed on the next start.
func TestChannelFullWALPersist(t *testing.T) {
	// Build a server that blocks until released so the channel fills up.
	unblock := make(chan struct{})
	var delivered int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-unblock
		atomic.AddInt64(&delivered, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)

	// We need to fill the channel. Use a very small channel by writing a
	// replacement queue with a capacity-1 channel — that's not exported.
	// Instead we directly test the WAL persist path by writing to a queue
	// that is not started (no drain goroutine).
	q2 := auditq.New(srv.URL, "token", wal)
	// Do NOT call Start() — the channel will eventually fill.
	// Enqueue 1 event — it should persist to WAL even if Start() not called.
	q2.Enqueue(newEvent("token.issued"))

	// Verify WAL file exists and contains the event.
	data, err := os.ReadFile(wal)
	if err != nil {
		t.Fatalf("WAL file not created: %v", err)
	}
	if len(data) == 0 {
		t.Fatal("WAL file is empty; event was not persisted")
	}

	// Now start a fresh queue that replays the WAL.
	close(unblock) // unblock the server
	q3 := auditq.New(srv.URL, "token", wal)
	q3.Replay()
	q3.Start()

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if atomic.LoadInt64(&delivered) >= 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	q3.Close()

	if atomic.LoadInt64(&delivered) < 1 {
		t.Fatalf("expected replayed event to be delivered")
	}
}

// ---------------------------------------------------------------------------
// TestRestartWithNonEmptyWALReplayDrains
// ---------------------------------------------------------------------------

func TestRestartWithNonEmptyWALReplayDrains(t *testing.T) {
	var count int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&count, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)

	// Phase 1: enqueue but do NOT start the drainer — simulate crash after WAL write.
	q := auditq.New(srv.URL, "tok", wal)
	q.Enqueue(newEvent("token.issued"))
	q.Enqueue(newEvent("proxy.hit"))
	// No Start() call — events sit in WAL only (channel not drained).

	// Phase 2: fresh queue simulating restart.
	q2 := auditq.New(srv.URL, "tok", wal)
	q2.Replay()
	q2.Start()

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if atomic.LoadInt64(&count) >= 2 {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	q2.Close()

	if atomic.LoadInt64(&count) < 2 {
		t.Fatalf("expected 2 replayed events, delivered %d", count)
	}
}

// ---------------------------------------------------------------------------
// TestShutdownDrainsInFlightWithDeadline
// ---------------------------------------------------------------------------

func TestShutdownDrainsInFlightWithDeadline(t *testing.T) {
	var count int64
	// Slight delay per event so drain deadline is exercised.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(5 * time.Millisecond)
		atomic.AddInt64(&count, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startQueue(t, srv, wal)

	for i := 0; i < 5; i++ {
		q.Enqueue(newEvent("token.issued"))
	}

	// Generous deadline — all 5 events should drain.
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	q.CloseWithContext(ctx)

	if atomic.LoadInt64(&count) < 5 {
		t.Fatalf("expected 5 events drained, got %d", count)
	}
}

// ---------------------------------------------------------------------------
// TestNetworkErrorRetryWithBackoff
// ---------------------------------------------------------------------------

func TestNetworkErrorRetryWithBackoff(t *testing.T) {
	var attempts int64
	// Fail the first 2 calls, succeed on the 3rd.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt64(&attempts, 1)
		if n < 3 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startQueue(t, srv, wal)
	q.Enqueue(newEvent("token.issued"))

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if atomic.LoadInt64(&attempts) >= 3 {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	q.Close()

	if atomic.LoadInt64(&attempts) < 3 {
		t.Fatalf("expected at least 3 attempts (2 failures + 1 success), got %d", attempts)
	}
}

// ---------------------------------------------------------------------------
// TestEnqueueNoCredentialsInPayload
// Verify the Event struct has no fields that could carry credential values.
// ---------------------------------------------------------------------------

func TestEnqueueNoCredentialsInPayload(t *testing.T) {
	forbidden := map[string]bool{
		"credential":  true,
		"api_key":     true,
		"secret":      true,
		"token_value": true,
	}

	// Serialise a zero-value Event and check the JSON keys.
	b, err := json.Marshal(auditq.Event{})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	for key := range m {
		if forbidden[key] {
			t.Errorf("Event JSON key %q is forbidden (S-SEC-1)", key)
		}
	}
}
