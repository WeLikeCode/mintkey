// Package auditq provides a local async audit-event queue with a disk
// write-ahead buffer (WAL).
//
// # Architecture
//
// Each service that emits audit events creates a Queue at startup.  The
// request path calls Enqueue, which is O(1): it appends a newline-delimited
// JSON record to the WAL file and sends the event to a buffered in-memory
// channel. A single background worker drains the channel and POSTs each event
// to admin-api's /v1/internal/audit/emit HTTP endpoint. On success the
// corresponding WAL line is cleared (overwritten with a zero-tombstone marker).
// On failure the event stays in the WAL and is retried with exponential
// back-off.
//
// Crash safety: if the process dies before draining, the WAL survives on disk.
// On the next startup, Replay reads any un-tombstoned lines and re-enqueues
// them.
//
// Graceful shutdown: Close drains in-flight events with a configurable
// deadline; anything not drained within the deadline remains in the WAL for
// the next startup.
//
// WAL compaction: a background goroutine periodically rewrites the WAL,
// removing tombstoned (delivered) lines.  Triggered by a timer (default 5m)
// or a size threshold (default 64 MiB), whichever fires first (#27).
//
// Dead-letter monitoring: Prometheus-format metrics are maintained via
// sync/atomic counters and exposed via WriteMetricsTo / MetricsHandler (#27).
//
// Design rules (ADR-0014.7; S-SEC-1):
//   - Payloads MUST NOT contain any credential plaintext (callers' responsibility).
//   - The queue does not enforce ordering across multiple service instances;
//     admin-api's audit_emit serialises concurrent appends via a per-tenant
//     advisory lock + SELECT FOR UPDATE on audit_chain_state.
//
// Source: #22 async audit emission; #27 WAL compaction + dead-letter metrics.
package auditq

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

const (
	// channelCap is the number of events that can queue in-memory before
	// Enqueue falls back to WAL-only (persist + warn, do not block).
	channelCap = 1000

	// walTombstone is written over a processed WAL line so replays skip it
	// without shrinking the file (truncation is out of scope — flagged as
	// follow-up).
	walTombstone = "~"

	// drainDeadlineDefault is used when Close is called without a context.
	drainDeadlineDefault = 5 * time.Second

	// maxRetryDelay caps the exponential back-off between admin-api calls.
	maxRetryDelay = 30 * time.Second

	// initialRetryDelay is the first back-off interval.
	initialRetryDelay = 250 * time.Millisecond

	// maxDeadLetterRetries is the number of consecutive failures before an
	// event is moved to the dead-letter file (same dir, ".dead" suffix).
	maxDeadLetterRetries = 5
)

// Event is the wire shape sent to admin-api's /v1/internal/audit/emit.
// Payload MUST NOT contain credential plaintext (S-SEC-1).
type Event struct {
	EventType  string         `json:"event_type"`
	TenantID   string         `json:"tenant_id"`
	ActorID    string         `json:"actor_id,omitempty"`
	ActorType  string         `json:"actor_type"`
	TargetID   string         `json:"target_id,omitempty"`
	TargetType string         `json:"target_type,omitempty"`
	Payload    map[string]any `json:"payload"`
}

// Queue is the async audit event queue.  Create one with New and call
// Enqueue from the request path.  Call Close on graceful shutdown.
type Queue struct {
	adminAPIURL  string
	serviceToken string
	walPath      string

	ch     chan Event
	httpC  *http.Client
	stopCh chan struct{}
	doneCh chan struct{}

	// walMu guards all WAL file I/O so concurrent Enqueue calls don't
	// interleave JSON lines.  compactWorker also acquires this mutex for the
	// read-filter-rename sequence, ensuring Enqueue never races with compaction.
	walMu sync.Mutex

	// metrics holds all Prometheus-format gauges and counters for this queue.
	metrics *Metrics

	// compactCfg controls when the compaction worker triggers.
	compactCfg CompactConfig
}

// New creates a Queue targeting adminAPIURL/v1/internal/audit/emit.
// serviceToken is sent in X-Mintkey-Service-Token on every request.
// walPath is the path to the WAL file (created on first Enqueue if absent).
//
// The serviceLabel is used as the Prometheus label value for {service="..."}
// on all auditq metrics.  Pass "broker" or "proxy-plugin" (or any identifier).
// If empty, the label is set to "unknown".
//
// Call Replay after New to drain any events left in the WAL from a previous
// run, then call Start to begin the background drainer.
func New(adminAPIURL, serviceToken, walPath string) *Queue {
	return NewWithConfig(adminAPIURL, serviceToken, walPath, "unknown", DefaultCompactConfig())
}

// NewWithConfig is like New but accepts an explicit service label for
// Prometheus metrics and a CompactConfig controlling the compaction policy.
func NewWithConfig(adminAPIURL, serviceToken, walPath, serviceLabel string, cc CompactConfig) *Queue {
	if serviceLabel == "" {
		serviceLabel = "unknown"
	}
	return &Queue{
		adminAPIURL:  adminAPIURL,
		serviceToken: serviceToken,
		walPath:      walPath,
		ch:           make(chan Event, channelCap),
		httpC:        &http.Client{Timeout: 10 * time.Second},
		stopCh:       make(chan struct{}),
		doneCh:       make(chan struct{}),
		metrics:      newMetrics(serviceLabel),
		compactCfg:   cc,
	}
}

// Replay reads the WAL file and re-enqueues any events that were not yet
// confirmed delivered (non-tombstone lines).  Call once after New, before
// Start.
func (q *Queue) Replay() {
	q.walMu.Lock()
	defer q.walMu.Unlock()

	f, err := os.Open(q.walPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return // nothing to replay
		}
		slog.Warn("auditq: replay: open WAL", "path", q.walPath, "err", err)
		return
	}
	defer func() { _ = f.Close() }()

	scanner := bufio.NewScanner(f)
	var replayed int
	for scanner.Scan() {
		line := scanner.Text()
		if strings.TrimSpace(line) == "" || strings.HasPrefix(line, walTombstone) {
			continue
		}
		var e Event
		if err := json.Unmarshal([]byte(line), &e); err != nil {
			slog.Warn("auditq: replay: unmarshal event", "line", line, "err", err)
			continue
		}
		select {
		case q.ch <- e:
			replayed++
		default:
			// Channel full on replay — very unlikely at startup, but log it.
			slog.Warn("auditq: replay: channel full, event queued at WAL-only level",
				"event_type", e.EventType)
		}
	}
	if replayed > 0 {
		slog.Info("auditq: replayed WAL events", "count", replayed, "wal", q.walPath)
	}
}

// Start launches the background drainer goroutine and the WAL compaction
// worker.  Call once after Replay.
func (q *Queue) Start() {
	go q.drain()
	go q.compactWorker(q.compactCfg)
}

// Enqueue appends event to the WAL (synchronous, durable) then sends it to
// the in-memory channel (O(1) non-blocking). If the channel is full the event
// is already persisted in the WAL and will be replayed on next startup; a
// warning is logged.
//
// Enqueue is safe to call concurrently.
func (q *Queue) Enqueue(e Event) {
	// 1. Write to WAL first — this is the durability guarantee.
	if err := q.appendWAL(e); err != nil {
		slog.Error("auditq: WAL write failed — event may be lost",
			"event_type", e.EventType, "err", err)
		// We still try the channel send below; worst case the event is
		// lost if the process dies before delivery.
	}

	// 2. Non-blocking channel send.
	select {
	case q.ch <- e:
	default:
		slog.Warn("auditq: channel full — event persisted in WAL, will drain later",
			"event_type", e.EventType)
	}
}

// Close signals the drainer to stop and waits up to drainDeadlineDefault for
// all queued events to be delivered.  Any undelivered events remain in the WAL
// for replay on the next startup.
func (q *Queue) Close() {
	ctx, cancel := context.WithTimeout(context.Background(), drainDeadlineDefault)
	defer cancel()
	q.CloseWithContext(ctx)
}

// CloseWithContext is like Close but uses the provided context for the drain
// deadline.
func (q *Queue) CloseWithContext(ctx context.Context) {
	close(q.stopCh)
	select {
	case <-q.doneCh:
	case <-ctx.Done():
		slog.Warn("auditq: shutdown deadline exceeded — remaining events in WAL will replay on restart",
			"wal", q.walPath)
	}
}

// appendWAL appends a newline-delimited JSON line to the WAL file.
func (q *Queue) appendWAL(e Event) error {
	b, err := json.Marshal(e)
	if err != nil {
		return fmt.Errorf("auditq: marshal event: %w", err)
	}

	q.walMu.Lock()
	defer q.walMu.Unlock()

	f, err := os.OpenFile(q.walPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("auditq: open WAL: %w", err)
	}
	defer func() { _ = f.Close() }()

	if _, err := f.Write(append(b, '\n')); err != nil {
		return fmt.Errorf("auditq: write WAL: %w", err)
	}
	return nil
}

// tombstoneWAL scans the WAL file and replaces the first occurrence of
// a line matching event with a tombstone marker.  This is a best-effort
// operation; failure is logged but not fatal.
func (q *Queue) tombstoneWAL(e Event) {
	target, err := json.Marshal(e)
	if err != nil {
		return
	}
	targetStr := string(target)

	q.walMu.Lock()
	defer q.walMu.Unlock()

	data, err := os.ReadFile(q.walPath)
	if err != nil {
		slog.Warn("auditq: tombstone: read WAL", "err", err)
		return
	}

	lines := strings.Split(string(data), "\n")
	replaced := false
	for i, line := range lines {
		if !replaced && strings.TrimSpace(line) == targetStr {
			lines[i] = walTombstone
			replaced = true
		}
	}
	if !replaced {
		return // line already gone or never persisted
	}

	if err := os.WriteFile(q.walPath, []byte(strings.Join(lines, "\n")), 0o600); err != nil {
		slog.Warn("auditq: tombstone: write WAL", "err", err)
	}
}

// deadLetterWAL appends the event to a side-file named <walPath>.dead so
// operators can inspect permanently failing events.  Only counts and file-size
// metadata are reflected in metrics — no plaintext from the event (S-SEC-1).
func (q *Queue) deadLetterWAL(e Event, lastErr error) {
	b, _ := json.Marshal(map[string]any{
		"event":    e,
		"last_err": lastErr.Error(),
		"at":       time.Now().UTC().Format(time.RFC3339),
	})
	path := q.walPath + ".dead"
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		slog.Error("auditq: dead-letter open", "err", err)
		return
	}
	defer func() { _ = f.Close() }()
	_, _ = f.Write(append(b, '\n'))

	// Increment dead-letter counter (count only — no payload content in metrics).
	q.metrics.deadLetterTotal.Add(1)

	// Refresh dead-letter file size gauge.
	if info, statErr := os.Stat(path); statErr == nil {
		q.metrics.deadLetterFileSizeBytes.Store(info.Size())
	}

	slog.Error("auditq: event moved to dead-letter file after max retries",
		"event_type", e.EventType, "dead_letter", path)
}

// drain is the background worker.  It pulls events from the channel and calls
// emit for each, with exponential back-off on failure.
func (q *Queue) drain() {
	defer close(q.doneCh)
	for {
		select {
		case e := <-q.ch:
			q.emitWithRetry(e)
		case <-q.stopCh:
			// Drain remaining in-flight events before exiting.
		drainLoop:
			for {
				select {
				case e := <-q.ch:
					q.emitWithRetry(e)
				default:
					break drainLoop
				}
			}
			return
		}
	}
}

// emitWithRetry calls emit and retries on failure with exponential back-off
// until maxDeadLetterRetries consecutive failures, after which the event is
// moved to the dead-letter file and tombstoned from the WAL.
func (q *Queue) emitWithRetry(e Event) {
	delay := initialRetryDelay
	for attempt := 1; attempt <= maxDeadLetterRetries; attempt++ {
		err := q.emit(e)
		if err == nil {
			q.tombstoneWAL(e)
			return
		}
		slog.Warn("auditq: emit failed",
			"event_type", e.EventType,
			"attempt", attempt,
			"err", err)
		if attempt < maxDeadLetterRetries {
			// Check if we've been asked to stop; honour shutdown deadline.
			select {
			case <-q.stopCh:
				// Best-effort: one more try then give up.
				if err2 := q.emit(e); err2 == nil {
					q.tombstoneWAL(e)
				}
				return
			case <-time.After(delay):
			}
			if delay < maxRetryDelay {
				delay *= 2
				if delay > maxRetryDelay {
					delay = maxRetryDelay
				}
			}
		}
	}
	q.tombstoneWAL(e)
	q.deadLetterWAL(e, fmt.Errorf("max retries exceeded"))
}

// TriggerCompact runs one compaction pass synchronously (blocking the caller
// until it completes).  Intended for tests and one-off operational use.
// Normal operation uses the background compactWorker.
func (q *Queue) TriggerCompact() {
	q.compact("manual")
}

// DeadLetterTotal returns the current value of the auditq_dead_letter_events_total
// counter (number of events moved to the dead-letter file since process start).
func (q *Queue) DeadLetterTotal() int64 {
	return q.metrics.deadLetterTotal.Load()
}

// DeadLetterFileSizeBytes returns the last-observed dead-letter file size in bytes.
func (q *Queue) DeadLetterFileSizeBytes() int64 {
	return q.metrics.deadLetterFileSizeBytes.Load()
}

// MetricsHandler returns an http.HandlerFunc that writes auditq metrics in
// Prometheus text exposition format (0.0.4).
func (q *Queue) MetricsHandler() http.HandlerFunc {
	return q.metrics.MetricsHandler()
}

// emit POSTs the event to admin-api's /v1/internal/audit/emit endpoint.
func (q *Queue) emit(e Event) error {
	body, err := json.Marshal(e)
	if err != nil {
		return fmt.Errorf("auditq: marshal event: %w", err)
	}

	req, err := http.NewRequestWithContext(
		context.Background(),
		http.MethodPost,
		q.adminAPIURL+"/v1/internal/audit/emit",
		bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("auditq: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", q.serviceToken)

	resp, err := q.httpC.Do(req)
	if err != nil {
		return fmt.Errorf("auditq: POST: %w", err)
	}
	defer func() {
		_, _ = io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
	}()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("auditq: emit returned HTTP %d", resp.StatusCode)
	}
	return nil
}
