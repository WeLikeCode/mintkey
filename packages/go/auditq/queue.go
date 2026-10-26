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
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
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

	// drainConcurrencyDefault is the number of delivery requests in flight.
	drainConcurrencyDefault = 4

	// drainBatchSizeDefault is the number of pending events read per pass.
	drainBatchSizeDefault = 1000

	// Environment variables that tune the drainer. An unset or empty value
	// takes its default; a value that is not an integer of at least 1 is
	// ignored with a warning.
	envDrainConcurrency = "MINTKEY_AUDIT_DRAIN_CONCURRENCY"
	envDrainBatchSize   = "MINTKEY_AUDIT_DRAIN_BATCH_SIZE"
	envRetryInitialMS   = "MINTKEY_AUDIT_RETRY_INITIAL_MS"
	envRetryMaxMS       = "MINTKEY_AUDIT_RETRY_MAX_MS"
)

// drainSettings holds the effective drainer settings read from the
// environment when the queue is built.
type drainSettings struct {
	concurrency  int
	batchSize    int
	initialDelay time.Duration
	maxDelay     time.Duration
}

// drainSettingsFromEnv reads the four drain-setting environment variables.
// Each unset or empty variable takes its default; each value that is not an
// integer of at least 1 is replaced by its default with one WARN record naming
// the variable. A maximum below the initial delay becomes the initial delay.
func drainSettingsFromEnv() drainSettings {
	s := drainSettings{
		concurrency:  drainConcurrencyDefault,
		batchSize:    drainBatchSizeDefault,
		initialDelay: initialRetryDelay,
		maxDelay:     maxRetryDelay,
	}
	if v, ok := positiveIntSetting(envDrainConcurrency); ok {
		s.concurrency = v
	}
	if v, ok := positiveIntSetting(envDrainBatchSize); ok {
		s.batchSize = v
	}
	if v, ok := positiveIntSetting(envRetryInitialMS); ok {
		s.initialDelay = time.Duration(v) * time.Millisecond
	}
	if v, ok := positiveIntSetting(envRetryMaxMS); ok {
		s.maxDelay = time.Duration(v) * time.Millisecond
	}
	if s.maxDelay < s.initialDelay {
		s.maxDelay = s.initialDelay
	}
	return s
}

// positiveIntSetting parses name as an integer of at least 1. It reports false
// for an unset or empty variable, and false after logging one WARN record for
// a set value that is not an integer of at least 1.
func positiveIntSetting(name string) (int, bool) {
	raw := os.Getenv(name)
	if raw == "" {
		return 0, false
	}
	v, err := strconv.Atoi(raw)
	if err != nil || v < 1 {
		slog.Warn("auditq: ignoring invalid setting", "name", name)
		return 0, false
	}
	return v, true
}

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

	// memCh holds events whose WAL append failed; they are delivered while
	// the process runs, as today.
	memCh chan Event

	// wakeCh is a capacity-1 signal to the drainer that new work exists. A
	// wake that would block is dropped because a wake is already pending.
	wakeCh chan struct{}

	httpC  *http.Client
	stopCh chan struct{}
	doneCh chan struct{}

	// walMu guards all WAL file I/O so concurrent Enqueue calls don't
	// interleave JSON lines.  compactWorker also acquires this mutex for the
	// read-filter-rename sequence, ensuring Enqueue never races with compaction.
	walMu sync.Mutex

	// deadMu serialises dead-letter appends so the file-size gauge reflects
	// the file after the last write, even when deliveries run concurrently.
	deadMu sync.Mutex

	// metrics holds all Prometheus-format gauges and counters for this queue.
	metrics *Metrics

	// compactCfg controls when the compaction worker triggers.
	compactCfg CompactConfig

	// settings holds the drainer settings read from the environment.
	settings drainSettings
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
		memCh:        make(chan Event, channelCap),
		wakeCh:       make(chan struct{}, 1),
		httpC:        &http.Client{Timeout: 10 * time.Second},
		stopCh:       make(chan struct{}),
		doneCh:       make(chan struct{}),
		metrics:      newMetrics(serviceLabel),
		compactCfg:   cc,
		settings:     drainSettingsFromEnv(),
	}
}

// Replay sets the backlog from the events that were not yet delivered or
// dead-lettered in the WAL. It delivers nothing itself: the drainer started by
// Start reads the WAL. Call once after New, before Start.
func (q *Queue) Replay() {
	q.walMu.Lock()
	data, err := os.ReadFile(q.walPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			q.metrics.backlogEvents.Store(0)
			q.walMu.Unlock()
			return // nothing to replay
		}
		q.walMu.Unlock()
		slog.Warn("auditq: replay: read WAL", "path", q.walPath, "err", err)
		return
	}
	pending := countPendingLines(data)
	q.metrics.backlogEvents.Store(pending)
	q.walMu.Unlock()

	if pending > 0 {
		slog.Info("auditq: WAL has pending events", "count", pending, "wal", q.walPath)
	}
}

// countPendingLines counts the lines of data that decode as an Event and are
// neither blank nor tombstoned. A fragment without a terminating newline is
// skipped until a later append terminates it.
func countPendingLines(data []byte) int64 {
	data = completeLines(data)
	var pending int64
	for _, raw := range bytes.Split(data, []byte("\n")) {
		line := strings.TrimSpace(string(raw))
		if line == "" || strings.HasPrefix(line, walTombstone) {
			continue
		}
		var e Event
		if err := json.Unmarshal(raw, &e); err != nil {
			continue
		}
		pending++
	}
	return pending
}

// completeLines drops an unterminated final line so that only whole lines are
// read; the fragment stays in the file until an append terminates it.
func completeLines(data []byte) []byte {
	if len(data) == 0 || data[len(data)-1] == '\n' {
		return data
	}
	idx := bytes.LastIndexByte(data, '\n')
	if idx < 0 {
		return nil
	}
	return data[:idx+1]
}

// Start launches the background drainer goroutine and the WAL compaction
// worker.  Call once after Replay.
func (q *Queue) Start() {
	s := q.settings
	slog.Info("auditq: drain settings",
		"service", q.metrics.serviceLabel,
		"concurrency", s.concurrency,
		"batch_size", s.batchSize,
		"initial_retry_delay", s.initialDelay,
		"max_retry_delay", s.maxDelay)
	go q.drain()
	go q.compactWorker(q.compactCfg)
}

// Enqueue appends event to the WAL (synchronous, durable), adds it to the
// backlog and wakes the drainer. When the append fails the event is held in
// the in-memory channel instead, so it is delivered while the process runs.
//
// Enqueue is safe to call concurrently.
func (q *Queue) Enqueue(e Event) {
	line, err := json.Marshal(e)
	if err != nil {
		slog.Error("auditq: marshal event — event lost",
			"event_type", e.EventType, "err", err)
		return
	}

	q.walMu.Lock()
	if werr := q.appendWALLocked(line); werr != nil {
		slog.Error("auditq: WAL write failed — holding event in memory",
			"event_type", e.EventType, "err", werr)
		select {
		case q.memCh <- e:
			q.metrics.backlogEvents.Add(1)
		default:
			slog.Error("auditq: memory queue full — event lost",
				"event_type", e.EventType)
		}
	} else {
		q.metrics.backlogEvents.Add(1)
	}
	q.walMu.Unlock()

	q.wake()
}

// wake tells the drainer that new work may exist. The channel has capacity 1,
// so a wake that would block is dropped: one wake is already pending.
func (q *Queue) wake() {
	select {
	case q.wakeCh <- struct{}{}:
	default:
	}
}

// closing reports whether Close has asked the drainer to stop.
func (q *Queue) closing() bool {
	select {
	case <-q.stopCh:
		return true
	default:
		return false
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

// appendWALLocked appends a newline-delimited JSON line to the WAL file. The
// caller holds walMu.
func (q *Queue) appendWALLocked(line []byte) error {
	f, err := os.OpenFile(q.walPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("auditq: open WAL: %w", err)
	}
	defer func() { _ = f.Close() }()

	if _, err := f.Write(append(line, '\n')); err != nil {
		return fmt.Errorf("auditq: write WAL: %w", err)
	}
	return nil
}

// tombstoneWAL scans the WAL file and replaces the first occurrence of
// a line matching event with a tombstone marker, then takes the event off the
// backlog.  It reports whether the event may be considered settled; a write
// failure leaves the line live so the event is retried.
func (q *Queue) tombstoneWAL(e Event) bool {
	target, err := json.Marshal(e)
	if err != nil {
		return false
	}
	targetStr := string(target)

	q.walMu.Lock()
	defer q.walMu.Unlock()

	data, err := os.ReadFile(q.walPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			q.metrics.backlogEvents.Add(-1)
			return true
		}
		slog.Warn("auditq: tombstone: read WAL", "err", err)
		return false
	}

	lines := strings.Split(string(data), "\n")
	replaced := false
	for i, line := range lines {
		if !replaced && strings.TrimSpace(line) == targetStr {
			lines[i] = walTombstone
			replaced = true
		}
	}
	if replaced {
		if err := os.WriteFile(q.walPath, []byte(strings.Join(lines, "\n")), 0o600); err != nil {
			slog.Warn("auditq: tombstone: write WAL", "err", err)
			return false
		}
	}

	q.metrics.backlogEvents.Add(-1)
	return true
}

// deadLetterWAL appends the event to a side-file named <walPath>.dead so
// operators can inspect permanently failing events.  Only counts and file-size
// metadata are reflected in metrics — no plaintext from the event (S-SEC-1).
func (q *Queue) deadLetterWAL(e Event, lastErr error) {
	q.deadMu.Lock()
	defer q.deadMu.Unlock()

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

	slog.Error("auditq: event moved to dead-letter file",
		"event_type", e.EventType, "dead_letter", path, "err", lastErr)
}

// batchEntry is one event read from the WAL or held in memory for delivery.
type batchEntry struct {
	event      Event
	fromMemory bool
	settled    bool
}

// drain is the background worker. It reads pending events from the WAL (plus
// the events held in memory), delivers them in rounds of up to the configured
// concurrency, and waits a capped, progress-based delay after a round in which
// nothing was delivered or refused.
func (q *Queue) drain() {
	defer close(q.doneCh)

	delay := q.settings.initialDelay
	for {
		batch := q.readBatch()
		if len(batch) == 0 {
			if q.closing() {
				return
			}
			select {
			case <-q.wakeCh:
				continue
			case <-q.stopCh:
				return
			}
		}

		progressed := false
		for i := 0; i < len(batch); {
			size := q.settings.concurrency
			if size > len(batch)-i {
				size = len(batch) - i
			}
			round := batch[i : i+size]
			i += size

			delivered, lastErr := q.deliverRound(round)
			if delivered > 0 {
				delay = q.settings.initialDelay
				progressed = true
				continue
			}
			if q.closing() {
				q.returnMemory(batch)
				return
			}

			next := nextRetryDelay(delay, q.settings.maxDelay)
			slog.Warn("auditq: drain round made no progress",
				"events", len(round),
				"delay", delay,
				"next_delay", next,
				"err", lastErr)
			if !q.waitDelay(delay) {
				q.returnMemory(batch)
				return
			}
			delay = next
		}

		q.returnMemory(batch)
		if q.closing() && !progressed {
			return
		}
	}
}

// readBatch reads up to the batch size of pending events from the WAL in file
// order, then every event waiting in the memory channel. It sets the backlog
// from the whole read (pending WAL events plus memory events), under walMu so
// that a concurrent append cannot race with the store.
func (q *Queue) readBatch() []*batchEntry {
	q.walMu.Lock()
	defer q.walMu.Unlock()

	entries := make([]*batchEntry, 0)
	var pending int64

	data, err := os.ReadFile(q.walPath)
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			slog.Warn("auditq: drain: read WAL", "path", q.walPath, "err", err)
		}
	} else {
		for _, raw := range bytes.Split(completeLines(data), []byte("\n")) {
			line := strings.TrimSpace(string(raw))
			if line == "" || strings.HasPrefix(line, walTombstone) {
				continue
			}
			var e Event
			if err := json.Unmarshal(raw, &e); err != nil {
				continue
			}
			pending++
			if len(entries) < q.settings.batchSize {
				entries = append(entries, &batchEntry{event: e})
			}
		}
	}

	for {
		select {
		case e := <-q.memCh:
			entries = append(entries, &batchEntry{event: e, fromMemory: true})
			pending++
		default:
			q.metrics.backlogEvents.Store(pending)
			return entries
		}
	}
}

// deliverRound delivers the entries of one round, one goroutine per entry, and
// settles each entry as soon as the sink answers it. It returns the number of
// events delivered or refused, and the first error of a retried entry.
func (q *Queue) deliverRound(entries []*batchEntry) (int, error) {
	var wg sync.WaitGroup
	var settled atomic.Int64
	var firstErr error
	var errMu sync.Mutex

	recordErr := func(err error) {
		errMu.Lock()
		if firstErr == nil {
			firstErr = err
		}
		errMu.Unlock()
	}

	for _, entry := range entries {
		wg.Add(1)
		go func(entry *batchEntry) {
			defer wg.Done()

			status, err := q.emit(entry.event)
			switch {
			case isRejected(status):
				if q.settleRejected(entry, status) {
					settled.Add(1)
				} else {
					recordErr(fmt.Errorf("auditq: dead-letter %s", entry.event.EventType))
				}
			case err == nil && status >= 200 && status < 300:
				if q.settleDelivered(entry) {
					settled.Add(1)
				} else {
					recordErr(fmt.Errorf("auditq: tombstone %s", entry.event.EventType))
				}
			default:
				if err == nil {
					err = fmt.Errorf("auditq: emit returned HTTP %d", status)
				}
				recordErr(err)
			}
		}(entry)
	}

	wg.Wait()
	return int(settled.Load()), firstErr
}

// settleDelivered settles an entry the sink accepted with a 2xx answer.
func (q *Queue) settleDelivered(entry *batchEntry) bool {
	if entry.fromMemory {
		q.walMu.Lock()
		q.metrics.backlogEvents.Add(-1)
		q.walMu.Unlock()
		entry.settled = true
		return true
	}
	if !q.tombstoneWAL(entry.event) {
		return false
	}
	entry.settled = true
	return true
}

// settleRejected dead-letters and tombstones an entry the sink refused.
func (q *Queue) settleRejected(entry *batchEntry, status int) bool {
	q.deadLetterWAL(entry.event, fmt.Errorf("rejected: HTTP %d", status))
	if entry.fromMemory {
		q.walMu.Lock()
		q.metrics.backlogEvents.Add(-1)
		q.walMu.Unlock()
		entry.settled = true
		return true
	}
	if !q.tombstoneWAL(entry.event) {
		return false
	}
	entry.settled = true
	return true
}

// returnMemory puts the memory events of batch that were neither delivered nor
// refused back into the memory channel, so a later pass retries them.
func (q *Queue) returnMemory(batch []*batchEntry) {
	for _, entry := range batch {
		if !entry.fromMemory || entry.settled {
			continue
		}
		select {
		case q.memCh <- entry.event:
		default:
			slog.Error("auditq: memory queue full — event lost",
				"event_type", entry.event.EventType)
		}
	}
}

// waitDelay waits d, returning false when the queue is closing.
func (q *Queue) waitDelay(d time.Duration) bool {
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-timer.C:
		return true
	case <-q.stopCh:
		return false
	}
}

// nextRetryDelay doubles current up to maxDelay. A non-positive current, or one
// already above half of maxDelay, jumps to maxDelay.
func nextRetryDelay(current, maxDelay time.Duration) time.Duration {
	if current <= 0 || current > maxDelay/2 {
		return maxDelay
	}
	return 2 * current
}

// isRejected reports whether status is a final refusal by the sink.
func isRejected(status int) bool {
	switch status {
	case http.StatusBadRequest, http.StatusRequestEntityTooLarge, http.StatusUnprocessableEntity:
		return true
	default:
		return false
	}
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

// emit POSTs the event to admin-api's /v1/internal/audit/emit endpoint. It
// returns the sink's HTTP status (0 when no answer was read) and an error for
// any answer that is not 2xx.
func (q *Queue) emit(e Event) (int, error) {
	body, err := json.Marshal(e)
	if err != nil {
		return 0, fmt.Errorf("auditq: marshal event: %w", err)
	}

	req, err := http.NewRequestWithContext(
		context.Background(),
		http.MethodPost,
		q.adminAPIURL+"/v1/internal/audit/emit",
		bytes.NewReader(body),
	)
	if err != nil {
		return 0, fmt.Errorf("auditq: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", q.serviceToken)

	resp, err := q.httpC.Do(req)
	if err != nil {
		return 0, fmt.Errorf("auditq: POST: %w", err)
	}
	defer func() {
		_, _ = io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
	}()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return resp.StatusCode, fmt.Errorf("auditq: emit returned HTTP %d", resp.StatusCode)
	}
	return resp.StatusCode, nil
}
