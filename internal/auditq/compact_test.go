// Package auditq_test — compaction and dead-letter monitoring tests.
//
// Source: #27 WAL rotation/compaction + dead-letter Prometheus metrics.
package auditq_test

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/internal/auditq"
)

// ---------------------------------------------------------------------------
// helpers (local to this file)
// ---------------------------------------------------------------------------

// startWithConfig is like startQueue but uses NewWithConfig to inject a custom
// CompactConfig (short intervals for testing).
func startWithConfig(t *testing.T, srv *httptest.Server, walPath string, cc auditq.CompactConfig) *auditq.Queue {
	t.Helper()
	q := auditq.NewWithConfig(srv.URL, "test-token", walPath, "test-svc", cc)
	q.Replay()
	q.Start()
	return q
}

// walLineCount returns (total lines, tombstone lines, live lines) for walPath.
func walLineCount(t *testing.T, walPath string) (total, tombstoned, live int) {
	t.Helper()
	data, err := os.ReadFile(walPath)
	if err != nil {
		return 0, 0, 0
	}
	for _, line := range strings.Split(string(data), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		total++
		if strings.HasPrefix(trimmed, "~") {
			tombstoned++
		} else {
			live++
		}
	}
	return
}

// ---------------------------------------------------------------------------
// TestCompactionShrinksWAL
//
// Enqueue 1000 events, drain 990, trigger manual compaction, verify the WAL
// shrinks and the remaining 10 events still drain successfully.
// ---------------------------------------------------------------------------

func TestCompactionShrinksWAL(t *testing.T) {
	const total = 1000
	const toDrain = 990
	const remaining = total - toDrain

	var delivered int64
	// Gate: first toDrain calls succeed; further calls block until unlocked.
	gate := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt64(&delivered, 1)
		if n <= toDrain {
			w.WriteHeader(http.StatusOK)
			return
		}
		// Block until gate is opened (simulates the last 10 events pending).
		<-gate
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	// Disable the background compact worker; we'll trigger compaction manually.
	cc := auditq.CompactConfig{IntervalSec: 0, ThresholdBytes: 0}
	wal := tmpWAL(t)
	q := startWithConfig(t, srv, wal, cc)

	for i := 0; i < total; i++ {
		q.Enqueue(newEvent(fmt.Sprintf("evt_%d", i)))
	}

	// Wait for first 990 to drain.
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if atomic.LoadInt64(&delivered) >= toDrain {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if atomic.LoadInt64(&delivered) < toDrain {
		t.Fatalf("only %d/%d events drained before compaction check", atomic.LoadInt64(&delivered), toDrain)
	}

	// Measure WAL size before compaction.
	before, err := os.Stat(wal)
	if err != nil {
		t.Fatalf("stat WAL: %v", err)
	}

	// Trigger a one-shot compaction via TriggerCompact.
	q.TriggerCompact()

	// Size must have decreased (990 tombstones removed).
	after, err := os.Stat(wal)
	if err != nil {
		t.Fatalf("stat WAL after compact: %v", err)
	}
	if after.Size() >= before.Size() {
		t.Fatalf("expected WAL to shrink: before=%d after=%d", before.Size(), after.Size())
	}

	// After compaction the WAL should contain exactly the remaining live events.
	_, _, live := walLineCount(t, wal)
	if live != remaining {
		t.Fatalf("expected %d live WAL lines after compaction, got %d", remaining, live)
	}

	// Unblock the server so the last 10 events drain.
	close(gate)
	deadline2 := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline2) {
		if atomic.LoadInt64(&delivered) >= total {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	q.Close()

	if atomic.LoadInt64(&delivered) < total {
		t.Fatalf("remaining events not drained after compaction: got %d want %d",
			atomic.LoadInt64(&delivered), total)
	}
}

// ---------------------------------------------------------------------------
// TestCompactionRace — 10 iterations, concurrent enqueue + drain + compact
//
// No event must be lost.  Run with -race to detect data races.
// ---------------------------------------------------------------------------

func TestCompactionRace(t *testing.T) {
	const iterations = 10
	const eventsPerIter = 200

	for iter := 0; iter < iterations; iter++ {
		t.Run(fmt.Sprintf("iter_%d", iter), func(t *testing.T) {
			var delivered int64
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				atomic.AddInt64(&delivered, 1)
				w.WriteHeader(http.StatusOK)
			}))
			defer srv.Close()

			// Very short compact interval to trigger compaction during drain.
			cc := auditq.CompactConfig{IntervalSec: 0, ThresholdBytes: 0}
			wal := tmpWAL(t)
			q := startWithConfig(t, srv, wal, cc)

			var wg sync.WaitGroup
			// Enqueue concurrently from multiple goroutines.
			for g := 0; g < 4; g++ {
				wg.Add(1)
				go func() {
					defer wg.Done()
					for i := 0; i < eventsPerIter/4; i++ {
						q.Enqueue(newEvent("race_event"))
					}
				}()
			}
			// Compact concurrently from another goroutine.
			wg.Add(1)
			go func() {
				defer wg.Done()
				for i := 0; i < 5; i++ {
					q.TriggerCompact()
					time.Sleep(5 * time.Millisecond)
				}
			}()
			wg.Wait()

			// Drain all events.
			deadline := time.Now().Add(15 * time.Second)
			for time.Now().Before(deadline) {
				if atomic.LoadInt64(&delivered) >= eventsPerIter {
					break
				}
				time.Sleep(20 * time.Millisecond)
			}
			q.Close()

			if atomic.LoadInt64(&delivered) < eventsPerIter {
				t.Fatalf("iter %d: event loss — delivered=%d want=%d",
					iter, atomic.LoadInt64(&delivered), eventsPerIter)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// TestCompactionThresholdTrigger
//
// Enqueue events until the WAL exceeds the threshold; verify compaction ran.
// ---------------------------------------------------------------------------

func TestCompactionThresholdTrigger(t *testing.T) {
	// 1 KiB threshold — very small so a few events push us over.
	const thresholdBytes = 1024

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cc := auditq.CompactConfig{
		IntervalSec:    0,                // disable timer
		ThresholdBytes: thresholdBytes,   // trigger on size
	}
	wal := tmpWAL(t)
	q := startWithConfig(t, srv, wal, cc)

	// Enqueue events with large payloads to quickly exceed the threshold.
	largePayload := strings.Repeat("x", 128)
	for i := 0; i < 20; i++ {
		q.Enqueue(auditq.Event{
			EventType: "big_event",
			TenantID:  "tenant_01",
			ActorType: "agent",
			Payload:   map[string]any{"data": largePayload},
		})
	}

	// Wait for drain so tombstones accumulate, then watch for the WAL to
	// grow past the threshold and then shrink (compaction fired).
	deadline := time.Now().Add(10 * time.Second)
	compactionObserved := false
	for time.Now().Before(deadline) {
		info, err := os.Stat(wal)
		if err != nil {
			time.Sleep(50 * time.Millisecond)
			continue
		}
		// Once file size drops back below threshold, compaction must have run.
		if info.Size() < thresholdBytes {
			compactionObserved = true
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	q.Close()

	if !compactionObserved {
		t.Fatal("expected compaction to reduce WAL below threshold, but it did not fire")
	}
}

// ---------------------------------------------------------------------------
// TestCompactionTimerTrigger
//
// With a very short interval, compaction runs even on an idle/small queue.
// ---------------------------------------------------------------------------

func TestCompactionTimerTrigger(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping timer test in short mode")
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	// 2-second compact interval so the test stays fast.
	cc := auditq.CompactConfig{IntervalSec: 2, ThresholdBytes: 0}
	wal := tmpWAL(t)
	q := startWithConfig(t, srv, wal, cc)

	// Enqueue a small batch and let them drain so the WAL has only tombstones.
	for i := 0; i < 5; i++ {
		q.Enqueue(newEvent("timer_evt"))
	}

	// Wait for drain.
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		_, tombstoned, _ := walLineCount(t, wal)
		if tombstoned >= 5 {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	// Now wait for the timer to fire and compact.
	deadline2 := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline2) {
		_, tombstoned, _ := walLineCount(t, wal)
		if tombstoned == 0 {
			break // all tombstones removed by compaction
		}
		time.Sleep(100 * time.Millisecond)
	}
	q.Close()

	_, tombstoned, _ := walLineCount(t, wal)
	if tombstoned > 0 {
		t.Fatalf("expected all tombstones compacted away, but %d remain", tombstoned)
	}
}

// ---------------------------------------------------------------------------
// TestDeadLetterMetrics
//
// Cause N events to dead-letter (mock returns errors every time).
// Verify: counter increments by N; file-size gauge matches actual file.
// ---------------------------------------------------------------------------

func TestDeadLetterMetrics(t *testing.T) {
	const wantDeadLettered = 3

	// Server always returns 500 so events exhaust retries → dead-letter.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	// Disable compaction so WAL is not touched.
	cc := auditq.CompactConfig{IntervalSec: 0, ThresholdBytes: 0}
	wal := tmpWAL(t)
	q := startWithConfig(t, srv, wal, cc)

	for i := 0; i < wantDeadLettered; i++ {
		q.Enqueue(newEvent(fmt.Sprintf("fail_evt_%d", i)))
	}

	// Wait until all events dead-letter (5 retries each × initial 250ms backoff
	// → max ~8s; use 30s deadline to be safe in CI).
	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		if q.DeadLetterTotal() >= wantDeadLettered {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	q.Close()

	gotTotal := q.DeadLetterTotal()
	if gotTotal != int64(wantDeadLettered) {
		t.Fatalf("dead-letter counter: want %d got %d", wantDeadLettered, gotTotal)
	}

	// Verify file size gauge matches actual file size.
	deadPath := wal + ".dead"
	info, err := os.Stat(deadPath)
	if err != nil {
		t.Fatalf("dead-letter file not found: %v", err)
	}
	if q.DeadLetterFileSizeBytes() != info.Size() {
		t.Fatalf("dead-letter file size gauge: want %d got %d",
			info.Size(), q.DeadLetterFileSizeBytes())
	}

	// Verify the dead-letter file lines are JSON and do NOT contain credential keys.
	data, _ := os.ReadFile(deadPath)
	for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
		if line == "" {
			continue
		}
		var m map[string]any
		if err := json.Unmarshal([]byte(line), &m); err != nil {
			t.Fatalf("dead-letter line is not valid JSON: %v", err)
		}
		for _, forbidden := range []string{"credential", "api_key", "secret", "token_value"} {
			if _, ok := m[forbidden]; ok {
				t.Errorf("dead-letter line contains forbidden key %q (S-SEC-1)", forbidden)
			}
		}
	}
}

// ---------------------------------------------------------------------------
// TestMetricsExposition
//
// Verify WriteMetricsTo emits all four expected metric families.
// ---------------------------------------------------------------------------

func TestMetricsExposition(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	cc := auditq.CompactConfig{IntervalSec: 0, ThresholdBytes: 0}
	wal := tmpWAL(t)
	q := startWithConfig(t, srv, wal, cc)
	q.Close()

	// Capture metrics output.
	rec := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/metrics", nil)
	q.MetricsHandler()(rec, req)

	body := rec.Body.String()
	expected := []string{
		"auditq_dead_letter_events_total",
		"auditq_dead_letter_file_size_bytes",
		"auditq_wal_size_bytes",
		"auditq_wal_pending_events",
		`service="test-svc"`,
	}
	for _, want := range expected {
		if !strings.Contains(body, want) {
			t.Errorf("metrics output missing %q\n--- output ---\n%s", want, body)
		}
	}
}

// ---------------------------------------------------------------------------
// TestCompactionNeverDropsUndelivered
//
// A stronger variant: enqueue 100 events, compact immediately (before drain
// starts), then drain and verify all 100 arrive.
// ---------------------------------------------------------------------------

func TestCompactionNeverDropsUndelivered(t *testing.T) {
	const total = 100
	var delivered int64

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Read body to avoid broken pipe
		_, _ = io.ReadAll(r.Body)
		atomic.AddInt64(&delivered, 1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)

	// Phase 1: enqueue without starting the drain (no Start call yet).
	q0 := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc",
		auditq.CompactConfig{IntervalSec: 0, ThresholdBytes: 0})
	for i := 0; i < total; i++ {
		q0.Enqueue(newEvent(fmt.Sprintf("pre_compact_%d", i)))
	}

	// Phase 2: compact the WAL (all events are undelivered, nothing should be removed).
	q0.TriggerCompact()

	// Verify all events survived compaction (live lines == total).
	_, _, live := walLineCount(t, wal)
	if live != total {
		t.Fatalf("compaction dropped events: expected %d live lines, got %d", total, live)
	}

	// Phase 3: replay + drain on a fresh queue.
	q1 := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc",
		auditq.CompactConfig{IntervalSec: 0, ThresholdBytes: 0})
	q1.Replay()
	q1.Start()

	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if atomic.LoadInt64(&delivered) >= total {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	q1.Close()

	if atomic.LoadInt64(&delivered) < total {
		t.Fatalf("event loss after compaction: delivered=%d want=%d",
			atomic.LoadInt64(&delivered), total)
	}
}
