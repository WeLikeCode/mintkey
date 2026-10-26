// Package auditq_test — durable WAL-backed delivery tests.
//
// Source: openspec/changes/audit-queue-durable, requirements "An undelivered
// event stays in the WAL until the sink accepts or refuses it", "Retries wait
// a capped delay that progress resets", "Deliveries run concurrently up to a
// bound, and failing events do not hold up the others" and "An event the sink
// refuses goes to the dead-letter file on its first answer".
package auditq_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/packages/go/auditq"
)

// seqEvent builds a proxy.hit event carrying {"seq": i}, as the durable
// scenarios describe.
func seqEvent(i int) auditq.Event {
	e := newEvent("proxy.hit")
	e.Payload = map[string]any{"seq": i}
	return e
}

// startDurable starts a queue labelled test-svc on walPath with background
// compaction disabled (the scenarios inspect the WAL's lines themselves).
func startDurable(t *testing.T, srv *httptest.Server, walPath string) *auditq.Queue {
	t.Helper()
	q := auditq.NewWithConfig(srv.URL, "test-token", walPath, "test-svc", auditq.CompactConfig{})
	q.Replay()
	q.Start()
	return q
}

// deadLetterExists reports whether <wal>.dead exists. It fails the test on a
// stat error other than not-exist.
func deadLetterExists(t *testing.T, walPath string) bool {
	t.Helper()
	_, err := os.Stat(walPath + ".dead")
	if err == nil {
		return true
	}
	if !os.IsNotExist(err) {
		t.Fatalf("stat %s.dead: %v", walPath, err)
	}
	return false
}

// TestSinkDownThenBack_C_ff7aad7b covers the scenario "the sink is down, then
// returns": 1,500 events stay in the WAL, counted by the backlog gauge, until
// the sink starts answering 200.
func TestSinkDownThenBack_C_ff7aad7b(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "5")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "20")

	const total = 1500

	var up atomic.Bool
	var failed atomic.Int64
	var mu sync.Mutex
	got := make(map[int]bool)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if !up.Load() {
			failed.Add(1)
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		var e auditq.Event
		if err := json.Unmarshal(body, &e); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		seq, _ := e.Payload["seq"].(float64)
		mu.Lock()
		got[int(seq)] = true
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startDurable(t, srv, wal)
	defer q.Close()

	for i := 0; i < total; i++ {
		q.Enqueue(seqEvent(i))
	}

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) && failed.Load() < 10 {
		time.Sleep(time.Millisecond)
	}
	if failed.Load() < 10 {
		t.Fatalf("sink answered %d requests with 503 within 3s, want at least 10", failed.Load())
	}

	if n := q.DeadLetterTotal(); n != 0 {
		t.Fatalf("before the switch: DeadLetterTotal = %d, want 0", n)
	}
	if deadLetterExists(t, wal) {
		t.Fatalf("before the switch: %s.dead exists", wal)
	}
	if n := backlogOf(t, q, "test-svc"); n != total {
		t.Fatalf("before the switch: backlog = %d, want %d", n, total)
	}

	up.Store(true)

	deadline = time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(got)
		mu.Unlock()
		if n == total {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}

	mu.Lock()
	n := len(got)
	missing := -1
	for i := 0; i < total; i++ {
		if !got[i] {
			missing = i
			break
		}
	}
	mu.Unlock()
	if n != total {
		t.Fatalf("after the switch: %d/%d seq values reached the sink within 30s (first missing %d)", n, total, missing)
	}

	deadline = time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) && backlogOf(t, q, "test-svc") != 0 {
		time.Sleep(5 * time.Millisecond)
	}
	if n := backlogOf(t, q, "test-svc"); n != 0 {
		t.Fatalf("after delivery: backlog = %d, want 0", n)
	}
	if deadLetterExists(t, wal) {
		t.Fatalf("after delivery: %s.dead exists", wal)
	}
}

// TestRetriesPastFiveFailures_C_339a52c5 covers the scenario "more failures
// than the old limit of five": a single event survives eight 500 answers and
// reaches the sink with a 200.
func TestRetriesPastFiveFailures_C_339a52c5(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "1")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "5")

	var requests, delivered atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if requests.Add(1) <= 8 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		delivered.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startDurable(t, srv, wal)
	defer q.Close()

	q.Enqueue(seqEvent(0))

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) && delivered.Load() == 0 {
		time.Sleep(time.Millisecond)
	}
	if delivered.Load() == 0 {
		t.Fatalf("event did not reach the sink with a 200 within 3s (%d 500 answers)", requests.Load())
	}
	if n := q.DeadLetterTotal(); n != 0 {
		t.Fatalf("DeadLetterTotal = %d, want 0", n)
	}
	if deadLetterExists(t, wal) {
		t.Fatalf("%s.dead exists", wal)
	}
}

// TestCloseWhileSinkDownKeepsEvents_C_377ec4fd covers the scenario "closing
// while the sink is down keeps the events": CloseWithContext returns by its
// deadline and leaves the three events live in the WAL for the next queue.
func TestCloseWhileSinkDownKeepsEvents_C_377ec4fd(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "5")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "20")

	var failed atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		failed.Add(1)
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startDurable(t, srv, wal)

	for i := 0; i < 3; i++ {
		q.Enqueue(seqEvent(i))
	}

	// Six failures is more than the "at least 2" the scenario needs, and it is
	// enough to expose a drainer that gives up after its five attempts: that
	// one has already dead-lettered an event by then.
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) && failed.Load() < 6 {
		time.Sleep(time.Millisecond)
	}
	if failed.Load() < 6 {
		t.Fatalf("sink answered %d requests with 503 within 5s, want at least 6", failed.Load())
	}

	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	q.CloseWithContext(ctx)
	if elapsed := time.Since(start); elapsed > 3*time.Second {
		t.Fatalf("CloseWithContext took %v, want at most 3s", elapsed)
	}

	if _, _, live := walLineCount(t, wal); live != 3 {
		t.Fatalf("WAL holds %d live lines after CloseWithContext, want 3", live)
	}
	if deadLetterExists(t, wal) {
		t.Fatalf("%s.dead exists after CloseWithContext", wal)
	}

	var mu sync.Mutex
	delivered := make(map[int]bool)
	srv2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var e auditq.Event
		if err := json.Unmarshal(body, &e); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		seq, _ := e.Payload["seq"].(float64)
		mu.Lock()
		delivered[int(seq)] = true
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv2.Close()

	q2 := startDurable(t, srv2, wal)
	defer q2.Close()

	deadline = time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(delivered)
		mu.Unlock()
		if n == 3 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}

	mu.Lock()
	n := len(delivered)
	mu.Unlock()
	if n != 3 {
		t.Fatalf("new queue on the same WAL delivered %d/3 events", n)
	}
}

// TestUnwritableWALDeliversFromMemory_C_aa2619c2 covers the scenario "a WAL
// that cannot be written": the two events are held in memory (and counted by
// the backlog) and reach the sink, after which the backlog is 0.
func TestUnwritableWALDeliversFromMemory_C_aa2619c2(t *testing.T) {
	skipOutsideShortMode(t)

	release := make(chan struct{})
	var once sync.Once
	unblock := func() { once.Do(func() { close(release) }) }

	var received, delivered atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.ReadAll(r.Body)
		received.Add(1)
		<-release
		delivered.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	defer unblock()

	// The parent directory does not exist, so every WAL append fails.
	wal := filepath.Join(t.TempDir(), "missing", "test.wal")
	q := startDurable(t, srv, wal)
	defer q.Close()

	q.Enqueue(seqEvent(0))
	q.Enqueue(seqEvent(1))

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) && received.Load() < 1 {
		time.Sleep(time.Millisecond)
	}
	if received.Load() < 1 {
		t.Fatalf("sink received no request; the events were not delivered from memory")
	}
	if n := backlogOf(t, q, "test-svc"); n != 2 {
		t.Fatalf("backlog while the two events are held in memory = %d, want 2", n)
	}

	unblock()

	deadline = time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if delivered.Load() == 2 && backlogOf(t, q, "test-svc") == 0 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	if n := delivered.Load(); n != 2 {
		t.Fatalf("sink received %d/2 events", n)
	}
	if n := backlogOf(t, q, "test-svc"); n != 0 {
		t.Fatalf("after delivery: backlog = %d, want 0", n)
	}
}

// TestRetryDelayDoublesUpToCap_C_e8b4f95d covers the scenario "the delay
// doubles up to the cap": with one request in flight the gaps between 503
// answers start at 10ms, double, and stay at the 40ms cap.
func TestRetryDelayDoublesUpToCap_C_e8b4f95d(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_DRAIN_CONCURRENCY", "1")
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "10")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "40")

	var mu sync.Mutex
	var arrivals []time.Time
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		mu.Lock()
		arrivals = append(arrivals, time.Now())
		mu.Unlock()
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startDurable(t, srv, wal)
	defer q.Close()

	q.Enqueue(seqEvent(0))

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(arrivals)
		mu.Unlock()
		if n >= 12 {
			break
		}
		time.Sleep(time.Millisecond)
	}

	mu.Lock()
	n := len(arrivals)
	var times []time.Time
	if n >= 12 {
		times = append(times, arrivals[:12]...)
	}
	mu.Unlock()
	if n < 12 {
		t.Fatalf("sink received %d requests within 3s, want 12", n)
	}

	for i := 1; i < len(times); i++ {
		gap := times[i].Sub(times[i-1])
		if gap < 10*time.Millisecond {
			t.Fatalf("gap %d between requests = %v, want at least 10ms", i, gap)
		}
		if gap > 150*time.Millisecond {
			t.Fatalf("gap %d between requests = %v, want at most 150ms", i, gap)
		}
		if i >= 3 && gap < 40*time.Millisecond {
			t.Fatalf("gap %d between requests = %v, want at least 40ms once the cap is reached", i, gap)
		}
	}
}

// TestConcurrencyIsBounded_C_d0d6b92f covers the scenario "the number of
// requests in flight is bounded": 30 events reach a 20ms sink with at most
// three requests at once.
func TestConcurrencyIsBounded_C_d0d6b92f(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_DRAIN_CONCURRENCY", "3")

	var inFlight, maxInFlight, delivered atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		n := inFlight.Add(1)
		for {
			most := maxInFlight.Load()
			if n <= most || maxInFlight.CompareAndSwap(most, n) {
				break
			}
		}
		time.Sleep(20 * time.Millisecond)
		inFlight.Add(-1)
		delivered.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startDurable(t, srv, wal)
	defer q.Close()

	for i := 0; i < 30; i++ {
		q.Enqueue(seqEvent(i))
	}

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) && delivered.Load() < 30 {
		time.Sleep(2 * time.Millisecond)
	}
	if n := delivered.Load(); n < 30 {
		t.Fatalf("sink received %d/30 events within 3s", n)
	}

	if got := maxInFlight.Load(); got < 2 || got > 3 {
		t.Fatalf("most requests in flight = %d, want 2 or 3", got)
	}
}

// TestRefusedEventsDoNotHoldUpOthers_C_2ea77966 covers the scenario "events the
// sink keeps answering with 403": the 30 others are delivered while the ten
// poison events stay pending, and the poison events arrive once released.
func TestRefusedEventsDoNotHoldUpOthers_C_2ea77966(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_DRAIN_CONCURRENCY", "4")
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "200")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "5000")

	var released atomic.Bool
	var poisonRejected atomic.Int64
	var mu sync.Mutex
	normals := make(map[int]bool)
	poison := make(map[int]bool)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var e auditq.Event
		if err := json.Unmarshal(body, &e); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		seq, _ := e.Payload["seq"].(float64)
		if e.Payload["kind"] == "poison" {
			if !released.Load() {
				poisonRejected.Add(1)
				w.WriteHeader(http.StatusForbidden)
				return
			}
			mu.Lock()
			poison[int(seq)] = true
			mu.Unlock()
			w.WriteHeader(http.StatusOK)
			return
		}
		mu.Lock()
		normals[int(seq)] = true
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startDurable(t, srv, wal)
	defer q.Close()

	seq := 0
	for i := 0; i < 10; i++ {
		p := newEvent("proxy.hit")
		p.Payload = map[string]any{"kind": "poison", "seq": seq}
		seq++
		q.Enqueue(p)
		for j := 0; j < 3; j++ {
			q.Enqueue(seqEvent(seq))
			seq++
		}
	}

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(normals)
		mu.Unlock()
		if n == 30 && backlogOf(t, q, "test-svc") == 10 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}

	mu.Lock()
	normalN := len(normals)
	mu.Unlock()
	back := backlogOf(t, q, "test-svc")
	if normalN != 30 || back != 10 {
		t.Fatalf("before the release: %d/30 other events delivered and backlog %d (want 10); poison 403 answers: %d",
			normalN, back, poisonRejected.Load())
	}
	if released.Load() {
		t.Fatal("test released the poison events before the check")
	}
	if poisonRejected.Load() == 0 {
		t.Fatal("poison events were never answered with 403")
	}

	released.Store(true)

	deadline = time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(poison)
		mu.Unlock()
		if n == 10 && backlogOf(t, q, "test-svc") == 0 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}

	mu.Lock()
	poisonN := len(poison)
	mu.Unlock()
	if poisonN != 10 {
		t.Fatalf("after the release: %d/10 poison events delivered within 10s", poisonN)
	}
	if n := backlogOf(t, q, "test-svc"); n != 0 {
		t.Fatalf("after the release: backlog = %d, want 0", n)
	}
	if n := q.DeadLetterTotal(); n != 0 {
		t.Fatalf("after the release: DeadLetterTotal = %d, want 0", n)
	}
	if deadLetterExists(t, wal) {
		t.Fatalf("%s.dead exists", wal)
	}
}

// TestRefusalStatuses_C_f33bec22 covers the scenario "which statuses are a
// refusal": 400, 413 and 422 are final; 200 and 204 deliver; every other
// status is retried. It stops at the first wrong status.
func TestRefusalStatuses_C_f33bec22(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "5")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "5")

	statuses := []int{
		http.StatusBadRequest,
		http.StatusRequestEntityTooLarge,
		http.StatusUnprocessableEntity,
		http.StatusOK,
		http.StatusNoContent,
		http.StatusUnauthorized,
		http.StatusForbidden,
		http.StatusNotFound,
		http.StatusConflict,
		http.StatusTooManyRequests,
		http.StatusInternalServerError,
		http.StatusBadGateway,
		http.StatusServiceUnavailable,
		http.StatusGatewayTimeout,
	}
	for _, status := range statuses {
		checkRefusalStatus(t, status)
	}
}

// checkRefusalStatus runs one status of TestRefusalStatuses with a fresh sink,
// WAL and queue, closing both before returning.
func checkRefusalStatus(t *testing.T, status int) {
	t.Helper()

	var requests atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		requests.Add(1)
		w.WriteHeader(status)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{})
	q.Replay()
	q.Start()
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		q.CloseWithContext(ctx)
	}()

	q.Enqueue(newEvent("token.issued"))

	switch status {
	case http.StatusBadRequest, http.StatusRequestEntityTooLarge, http.StatusUnprocessableEntity:
		deadline := time.Now().Add(2 * time.Second)
		for time.Now().Before(deadline) && q.DeadLetterTotal() < 1 {
			time.Sleep(time.Millisecond)
		}
		if n := q.DeadLetterTotal(); n != 1 {
			t.Fatalf("status %d: DeadLetterTotal = %d after 2s, want 1", status, n)
		}
		time.Sleep(100 * time.Millisecond)
		if n := requests.Load(); n != 1 {
			t.Fatalf("status %d: sink received %d requests, want exactly 1", status, n)
		}
	case http.StatusOK, http.StatusNoContent:
		deadline := time.Now().Add(2 * time.Second)
		for time.Now().Before(deadline) {
			if _, _, live := walLineCount(t, wal); live == 0 {
				break
			}
			time.Sleep(time.Millisecond)
		}
		if _, _, live := walLineCount(t, wal); live != 0 {
			t.Fatalf("status %d: WAL still has %d live lines after 2s", status, live)
		}
		if deadLetterExists(t, wal) {
			t.Fatalf("status %d: %s.dead exists", status, wal)
		}
	default:
		deadline := time.Now().Add(2 * time.Second)
		for time.Now().Before(deadline) && requests.Load() < 3 {
			time.Sleep(time.Millisecond)
		}
		if n := requests.Load(); n < 3 {
			t.Fatalf("status %d: sink received %d requests within 2s, want at least 3", status, n)
		}
		if n := q.DeadLetterTotal(); n != 0 {
			t.Fatalf("status %d: DeadLetterTotal = %d, want 0", status, n)
		}
		if deadLetterExists(t, wal) {
			t.Fatalf("status %d: %s.dead exists", status, wal)
		}
	}
}

// TestRefusedEventRecord_C_8c6da99a covers the scenario "the record of a
// refused event": the dead-letter line names token.issued and the 422 refusal,
// while the backlog and the WAL's live lines are empty.
func TestRefusedEventRecord_C_8c6da99a(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "5")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "5")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := startDurable(t, srv, wal)
	defer q.Close()

	q.Enqueue(newEvent("token.issued"))

	deadPath := wal + ".dead"
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		data, err := os.ReadFile(deadPath)
		if err == nil && strings.TrimSpace(string(data)) != "" {
			if _, _, live := walLineCount(t, wal); live == 0 && backlogOf(t, q, "test-svc") == 0 {
				break
			}
		}
		time.Sleep(time.Millisecond)
	}

	data, err := os.ReadFile(deadPath)
	if err != nil {
		t.Fatalf("read %s within 2s: %v", deadPath, err)
	}
	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(lines) != 1 || lines[0] == "" {
		t.Fatalf("%s holds %d lines, want exactly 1", deadPath, len(lines))
	}

	var record struct {
		Event   auditq.Event `json:"event"`
		LastErr string       `json:"last_err"`
	}
	if err := json.Unmarshal([]byte(lines[0]), &record); err != nil {
		t.Fatalf("dead-letter line is not JSON: %v", err)
	}
	if record.Event.EventType != "token.issued" {
		t.Fatalf("dead-letter event_type = %q, want token.issued", record.Event.EventType)
	}
	if record.LastErr != "rejected: HTTP 422" {
		t.Fatalf("dead-letter last_err = %q, want %q", record.LastErr, "rejected: HTTP 422")
	}
	if n := backlogOf(t, q, "test-svc"); n != 0 {
		t.Fatalf("backlog = %d, want 0", n)
	}
	if _, _, live := walLineCount(t, wal); live != 0 {
		t.Fatalf("WAL holds %d live lines, want 0", live)
	}
}
