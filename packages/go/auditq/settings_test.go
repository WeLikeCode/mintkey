// Package auditq_test — drain settings tests.
//
// Source: openspec/changes/audit-queue-durable, requirement "Retries wait a
// capped delay that progress resets".
package auditq_test

import (
	"bytes"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/mintkey/mintkey/packages/go/auditq"
)

// drainSettingVars are the four environment variables the queue reads when it
// is built, in the order the settings record names them.
var drainSettingVars = []string{
	"MINTKEY_AUDIT_DRAIN_CONCURRENCY",
	"MINTKEY_AUDIT_DRAIN_BATCH_SIZE",
	"MINTKEY_AUDIT_RETRY_INITIAL_MS",
	"MINTKEY_AUDIT_RETRY_MAX_MS",
}

// lockedBuffer is an io.Writer safe for the drainer and test goroutines.
type lockedBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *lockedBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *lockedBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.String()
}

// captureDefaultLogger replaces the default slog logger with a text handler
// writing to a locked buffer and restores the previous default afterwards.
func captureDefaultLogger(t *testing.T) *lockedBuffer {
	t.Helper()
	buf := &lockedBuffer{}
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewTextHandler(buf, nil)))
	t.Cleanup(func() { slog.SetDefault(prev) })
	return buf
}

// startSettingsQueue builds and starts a queue labelled test-svc on a fresh WAL
// with a sink that answers 200, closing both before the test ends.
func startSettingsQueue(t *testing.T) {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	q := auditq.NewWithConfig(srv.URL, "test-token", tmpWAL(t), "test-svc", auditq.CompactConfig{})
	q.Replay()
	q.Start()
	t.Cleanup(q.Close)
}

// logLineContaining returns the first non-empty line of text that contains all
// of the given substrings, or "" when there is none.
func logLineContaining(text string, parts ...string) string {
	for _, line := range strings.Split(text, "\n") {
		if line == "" {
			continue
		}
		matches := true
		for _, part := range parts {
			if !strings.Contains(line, part) {
				matches = false
				break
			}
		}
		if matches {
			return line
		}
	}
	return ""
}

// TestDrainSettingsDefaults_C_ea45dc31 covers the scenario "the defaults": an
// empty value counts as unset, so the settings record names the four defaults.
func TestDrainSettingsDefaults_C_ea45dc31(t *testing.T) {
	skipOutsideShortMode(t)

	buf := captureDefaultLogger(t)
	for _, name := range drainSettingVars {
		t.Setenv(name, "")
	}

	startSettingsQueue(t)

	const want = `msg="auditq: drain settings" service=test-svc concurrency=4 batch_size=1000 initial_retry_delay=250ms max_retry_delay=30s`
	if !strings.Contains(buf.String(), want) {
		t.Fatalf("log has no settings record %q:\n%s", want, buf.String())
	}
}

// TestDrainSettingsFromEnvironment_C_be765c63 covers the scenario "set values,
// and a maximum below the initial delay": the record names the set values and
// the maximum is raised to the initial delay.
func TestDrainSettingsFromEnvironment_C_be765c63(t *testing.T) {
	skipOutsideShortMode(t)

	t.Setenv("MINTKEY_AUDIT_DRAIN_CONCURRENCY", "2")
	t.Setenv("MINTKEY_AUDIT_DRAIN_BATCH_SIZE", "10")
	t.Setenv("MINTKEY_AUDIT_RETRY_INITIAL_MS", "1000")
	t.Setenv("MINTKEY_AUDIT_RETRY_MAX_MS", "1")

	buf := captureDefaultLogger(t)
	startSettingsQueue(t)

	const want = `msg="auditq: drain settings" service=test-svc concurrency=2 batch_size=10 initial_retry_delay=1s max_retry_delay=1s`
	if !strings.Contains(buf.String(), want) {
		t.Fatalf("log has no settings record %q:\n%s", want, buf.String())
	}
}

// TestDrainSettingsInvalidValues_C_0b97502f covers the scenario "invalid
// values": every bad value falls back to its default and gets one WARN record
// naming the variable.
func TestDrainSettingsInvalidValues_C_0b97502f(t *testing.T) {
	skipOutsideShortMode(t)

	invalid := map[string]string{
		"MINTKEY_AUDIT_DRAIN_CONCURRENCY": "abc",
		"MINTKEY_AUDIT_DRAIN_BATCH_SIZE":  "-5",
		"MINTKEY_AUDIT_RETRY_INITIAL_MS":  "0",
		"MINTKEY_AUDIT_RETRY_MAX_MS":      "x",
	}
	for _, name := range drainSettingVars {
		t.Setenv(name, invalid[name])
	}

	buf := captureDefaultLogger(t)
	startSettingsQueue(t)

	logs := buf.String()
	const want = `msg="auditq: drain settings" service=test-svc concurrency=4 batch_size=1000 initial_retry_delay=250ms max_retry_delay=30s`
	if !strings.Contains(logs, want) {
		t.Fatalf("log has no settings record with the defaults %q:\n%s", want, logs)
	}

	for _, name := range drainSettingVars {
		line := logLineContaining(logs, "level=WARN", `msg="auditq: ignoring invalid setting"`, "name="+name)
		if line == "" {
			t.Fatalf("log has no WARN record %q naming %s:\n%s",
				"auditq: ignoring invalid setting", name, logs)
		}
	}
}
