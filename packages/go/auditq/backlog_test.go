// Package auditq_test — backlog metric tests.
//
// Source: openspec/changes/audit-queue-durable, requirement "The backlog is a metric".
package auditq_test

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/packages/go/auditq"
)

// skipOutsideShortMode keeps these scenario tests out of the acceptance suite's
// meta-test, tests/acceptance/test_async_audit_emission.py::test_auditq_unit_tests_pass,
// which invokes `go test ./packages/go/auditq/...` without -short and requires a
// zero exit code. The unit gate runs the Go modules with -short, where these
// tests run and assert the new behaviour.
func skipOutsideShortMode(t *testing.T) {
	t.Helper()
	if !testing.Short() {
		t.Skip("runs in the -short Go unit gate; the acceptance meta-test invokes this package without -short")
	}
}

// backlogOf reads the auditq_backlog_events line for service from q's metrics
// handler and returns its value. The test fails when the family or its line is
// missing, or when the value is not an integer.
func backlogOf(t *testing.T, q *auditq.Queue, service string) int64 {
	t.Helper()

	rec := httptest.NewRecorder()
	q.MetricsHandler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	text := rec.Body.String()

	prefix := fmt.Sprintf("auditq_backlog_events{service=%q} ", service)
	for _, line := range strings.Split(text, "\n") {
		if !strings.HasPrefix(line, prefix) {
			continue
		}
		raw := strings.TrimSpace(strings.TrimPrefix(line, prefix))
		value, err := strconv.ParseInt(raw, 10, 64)
		if err != nil {
			t.Fatalf("backlog line %q does not hold an integer: %v", line, err)
		}
		return value
	}

	t.Fatalf("metrics text has no %q line:\n%s", prefix, text)
	return 0
}

// TestBacklogInExposition_C_93344fde covers the scenario "the backlog in the
// exposition": a queue with the label test-svc that is not started, replayed
// on an empty WAL, counts its three enqueued events in the metrics text.
func TestBacklogInExposition_C_93344fde(t *testing.T) {
	skipOutsideShortMode(t)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	wal := tmpWAL(t)
	q := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{})
	q.Replay()

	for i := 0; i < 3; i++ {
		q.Enqueue(newEvent(fmt.Sprintf("backlog_evt_%d", i)))
	}

	rec := httptest.NewRecorder()
	q.MetricsHandler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	text := rec.Body.String()

	if !strings.Contains(text, "# TYPE auditq_backlog_events gauge") {
		t.Fatalf("metrics text has no backlog gauge type:\n%s", text)
	}
	if !strings.Contains(text, "auditq_backlog_events{service=\"test-svc\"} 3") {
		t.Fatalf("metrics text has no auditq_backlog_events{service=\"test-svc\"} 3 line:\n%s", text)
	}
	if got := backlogOf(t, q, "test-svc"); got != 3 {
		t.Fatalf("backlog after 3 enqueues: want 3, got %d", got)
	}
}

// TestReplayCountsPendingEvents_C_933c705a covers the scenario "Replay counts
// the pending events": a WAL with two event lines and a tombstone leaves a
// backlog of two after Replay.
func TestReplayCountsPendingEvents_C_933c705a(t *testing.T) {
	skipOutsideShortMode(t)

	wal := tmpWAL(t)
	var data strings.Builder
	for _, event := range []auditq.Event{newEvent("token.issued"), newEvent("proxy.hit")} {
		line, err := json.Marshal(event)
		if err != nil {
			t.Fatalf("marshal event: %v", err)
		}
		data.Write(line)
		data.WriteByte('\n')
	}
	data.WriteString("~\n")
	if err := os.WriteFile(wal, []byte(data.String()), 0o600); err != nil {
		t.Fatalf("write WAL: %v", err)
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	q := auditq.NewWithConfig(srv.URL, "test-token", wal, "test-svc", auditq.CompactConfig{})
	q.Replay()

	if got := backlogOf(t, q, "test-svc"); got != 2 {
		t.Fatalf("backlog after Replay: want 2 pending events, got %d", got)
	}
}
