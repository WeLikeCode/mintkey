// Package auditq_test — WAL format compatibility tests.
//
// Source: openspec/changes/audit-queue-durable, requirement "The WAL keeps the
// format the current code reads".
package auditq_test

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/packages/go/auditq"
)

// walEventLine returns the exact WAL line of e (json.Marshal without the
// trailing newline).
func walEventLine(t *testing.T, e auditq.Event) []byte {
	t.Helper()
	line, err := json.Marshal(e)
	if err != nil {
		t.Fatalf("marshal event: %v", err)
	}
	return line
}

// walLiveLines returns the non-blank, non-tombstoned lines of walPath.
func walLiveLines(t *testing.T, walPath string) []string {
	t.Helper()
	data, err := os.ReadFile(walPath)
	if err != nil {
		t.Fatalf("read WAL: %v", err)
	}
	var live []string
	for _, line := range strings.Split(string(data), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "~") {
			continue
		}
		live = append(live, line)
	}
	return live
}

// TestCurrentFormatWALDrainsInPlace_C_c0a8fbe4 covers the scenario "a WAL in
// today's format drains in place": a hand-written WAL drains in place without
// shrinking, and no payload bytes remain in the file.
func TestCurrentFormatWALDrainsInPlace_C_c0a8fbe4(t *testing.T) {
	skipOutsideShortMode(t)

	eventA := newEvent("token.issued")
	eventA.Payload = map[string]any{"marker": "alpha-payload"}
	eventB := newEvent("proxy.hit")
	lineA := walEventLine(t, eventA)
	lineB := walEventLine(t, eventB)

	wal := tmpWAL(t)
	content := string(lineA) + "\n~\n\n" + string(lineB) + "\n"
	if err := os.WriteFile(wal, []byte(content), 0o600); err != nil {
		t.Fatalf("write WAL: %v", err)
	}
	before, err := os.Stat(wal)
	if err != nil {
		t.Fatalf("stat WAL: %v", err)
	}
	sizeBefore := before.Size()

	var mu sync.Mutex
	bodies := make(map[string]bool)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		mu.Lock()
		bodies[string(body)] = true
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	q := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{})
	q.Replay()
	q.Start()
	defer q.Close()

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(bodies)
		mu.Unlock()
		if n == 2 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}

	mu.Lock()
	gotA := bodies[string(lineA)]
	gotB := bodies[string(lineB)]
	n := len(bodies)
	mu.Unlock()
	if !gotA || !gotB || n != 2 {
		t.Fatalf("sink received %d bodies; the two event lines arrived = A:%v B:%v", n, gotA, gotB)
	}

	deadline = time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) && backlogOf(t, q, "test-svc") != 0 {
		time.Sleep(5 * time.Millisecond)
	}
	if n := backlogOf(t, q, "test-svc"); n != 0 {
		t.Fatalf("after delivery: backlog = %d, want 0", n)
	}

	after, err := os.Stat(wal)
	if err != nil {
		t.Fatalf("stat WAL after delivery: %v", err)
	}
	if after.Size() != sizeBefore {
		t.Fatalf("WAL size after delivery = %d, want the original %d", after.Size(), sizeBefore)
	}

	data, err := os.ReadFile(wal)
	if err != nil {
		t.Fatalf("read WAL after delivery: %v", err)
	}
	for _, line := range strings.Split(string(data), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		if !strings.HasPrefix(trimmed, "~") {
			t.Fatalf("WAL still holds a live line %q after delivery", line)
		}
	}
	if bytes.Contains(data, []byte("alpha-payload")) {
		t.Fatalf("WAL still contains the delivered payload:\n%s", data)
	}
}

// TestCompactionBetweenReadAndTombstone_C_88d9b9f7 covers the scenario
// "compaction between the read and the tombstone": a compaction that moves the
// held event's line does not stop its later tombstone or redeliver it.
func TestCompactionBetweenReadAndTombstone_C_88d9b9f7(t *testing.T) {
	skipOutsideShortMode(t)
	t.Setenv("MINTKEY_AUDIT_DRAIN_CONCURRENCY", "1")

	held := make(chan struct{})
	release := make(chan struct{})
	var heldOnce sync.Once
	var releaseOnce sync.Once
	unblock := func() { releaseOnce.Do(func() { close(release) }) }
	var heldDeliveries atomic.Int64

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var e auditq.Event
		if err := json.Unmarshal(body, &e); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if e.EventType == "hold.me" {
			heldOnce.Do(func() { close(held) })
			<-release
			heldDeliveries.Add(1)
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	t.Cleanup(unblock)

	wal := tmpWAL(t)
	q := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{})
	q.Replay()
	q.Start()
	defer q.Close()

	q.Enqueue(newEvent("first.event"))
	q.Enqueue(newEvent("second.event"))
	q.Enqueue(newEvent("hold.me"))

	select {
	case <-held:
	case <-time.After(3 * time.Second):
		t.Fatal("the hold.me request was not held within 3s")
	}

	// Compact while the third request is in flight, so the line the drainer
	// read is no longer at the offset it remembers.
	q.TriggerCompact()

	live := walLiveLines(t, wal)
	if len(live) != 1 {
		t.Fatalf("after compaction the WAL holds %d live lines, want the held event only:\n%q", len(live), live)
	}
	var only auditq.Event
	if err := json.Unmarshal([]byte(live[0]), &only); err != nil {
		t.Fatalf("the WAL's only live line is not an event: %v", err)
	}
	if only.EventType != "hold.me" {
		t.Fatalf("after compaction the WAL holds %q, want hold.me", only.EventType)
	}

	unblock()

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if backlogOf(t, q, "test-svc") == 0 && len(walLiveLines(t, wal)) == 0 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	if n := backlogOf(t, q, "test-svc"); n != 0 {
		t.Fatalf("after the release: backlog = %d, want 0", n)
	}
	if live := walLiveLines(t, wal); len(live) != 0 {
		t.Fatalf("after the release: WAL holds %d live lines, want 0", len(live))
	}

	time.Sleep(200 * time.Millisecond)
	if n := heldDeliveries.Load(); n != 1 {
		t.Fatalf("the sink received the held event %d times, want exactly 1", n)
	}
}

// TestUnreadableLineDeadLettered_C_84b4a061 covers the scenario "an unreadable
// line": a line that does not decode as an Event is dead-lettered once, while
// the readable event after it is delivered.
func TestUnreadableLineDeadLettered_C_84b4a061(t *testing.T) {
	skipOutsideShortMode(t)

	eventB := newEvent("proxy.hit")
	lineB := walEventLine(t, eventB)

	wal := tmpWAL(t)
	if err := os.WriteFile(wal, []byte("not json\n"+string(lineB)+"\n"), 0o600); err != nil {
		t.Fatalf("write WAL: %v", err)
	}

	var mu sync.Mutex
	delivered := make(map[string]bool)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var e auditq.Event
		if err := json.Unmarshal(body, &e); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		mu.Lock()
		delivered[e.EventType] = true
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	q := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{})
	q.Replay()
	q.Start()
	defer q.Close()

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		gotB := delivered["proxy.hit"]
		mu.Unlock()
		if gotB {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	mu.Lock()
	gotB := delivered["proxy.hit"]
	mu.Unlock()
	if !gotB {
		t.Fatal("event B did not reach the sink within 3s")
	}

	deadPath := wal + ".dead"
	var record struct {
		Line    string `json:"line"`
		LastErr string `json:"last_err"`
	}
	deadline = time.Now().Add(2 * time.Second)
	for {
		data, err := os.ReadFile(deadPath)
		if err == nil && strings.TrimSpace(string(data)) != "" {
			line := strings.SplitN(strings.TrimSpace(string(data)), "\n", 2)[0]
			if err := json.Unmarshal([]byte(line), &record); err == nil {
				break
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("no readable dead-letter record within 2s (read error: %v)", err)
		}
		time.Sleep(5 * time.Millisecond)
	}
	if record.Line != "not json" {
		t.Fatalf("dead-letter line = %q, want %q", record.Line, "not json")
	}
	if record.LastErr != "unreadable WAL line" {
		t.Fatalf("dead-letter last_err = %q, want %q", record.LastErr, "unreadable WAL line")
	}
	if n := q.DeadLetterTotal(); n != 1 {
		t.Fatalf("DeadLetterTotal = %d, want 1", n)
	}

	deadline = time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) && backlogOf(t, q, "test-svc") != 0 {
		time.Sleep(5 * time.Millisecond)
	}
	if n := backlogOf(t, q, "test-svc"); n != 0 {
		t.Fatalf("backlog = %d, want 0", n)
	}
}

// TestAppendAfterPartialLineStartsNewLine_C_306d3e39 covers the scenario "an
// append after a partial last line": the append terminates the fragment first,
// so the next event starts on its own line and the fragment is dead-lettered.
func TestAppendAfterPartialLineStartsNewLine_C_306d3e39(t *testing.T) {
	skipOutsideShortMode(t)

	eventA := newEvent("token.issued")
	lineA := walEventLine(t, eventA)
	eventB := newEvent("proxy.hit")
	lineB := walEventLine(t, eventB)

	const fragment = `{"event_type":"tok`

	wal := tmpWAL(t)
	if err := os.WriteFile(wal, []byte(string(lineA)+"\n"+fragment), 0o600); err != nil {
		t.Fatalf("write WAL: %v", err)
	}

	var mu sync.Mutex
	delivered := make(map[string]bool)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var e auditq.Event
		if err := json.Unmarshal(body, &e); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		mu.Lock()
		delivered[e.EventType] = true
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	q := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{})

	// The queue is not started yet: Enqueue alone must terminate the fragment.
	q.Enqueue(eventB)

	data, err := os.ReadFile(wal)
	if err != nil {
		t.Fatalf("read WAL after Enqueue: %v", err)
	}
	want := string(lineA) + "\n" + fragment + "\n" + string(lineB) + "\n"
	if string(data) != want {
		t.Fatalf("WAL after Enqueue =\n%q\nwant\n%q", data, want)
	}

	q.Replay()
	q.Start()
	defer q.Close()

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		gotA := delivered["token.issued"]
		gotB := delivered["proxy.hit"]
		mu.Unlock()
		if gotA && gotB {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	mu.Lock()
	gotA := delivered["token.issued"]
	gotB := delivered["proxy.hit"]
	mu.Unlock()
	if !gotA || !gotB {
		t.Fatalf("sink received A:%v B:%v, want both", gotA, gotB)
	}

	deadPath := wal + ".dead"
	var record struct {
		Line    string `json:"line"`
		LastErr string `json:"last_err"`
	}
	deadline = time.Now().Add(2 * time.Second)
	for {
		deadData, readErr := os.ReadFile(deadPath)
		if readErr == nil && strings.TrimSpace(string(deadData)) != "" {
			line := strings.SplitN(strings.TrimSpace(string(deadData)), "\n", 2)[0]
			if err := json.Unmarshal([]byte(line), &record); err == nil {
				break
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("no readable dead-letter record for the fragment within 2s (read error: %v)", readErr)
		}
		time.Sleep(5 * time.Millisecond)
	}
	if record.Line != fragment {
		t.Fatalf("dead-letter line = %q, want %q", record.Line, fragment)
	}
	if record.LastErr != "unreadable WAL line" {
		t.Fatalf("dead-letter last_err = %q, want %q", record.LastErr, "unreadable WAL line")
	}
}
