// Package auditq — WAL compaction (rotation/truncation).
//
// Compaction rewrites the WAL file to remove tombstoned (delivered) lines
// while preserving all undelivered events.  It runs on a background goroutine
// triggered by whichever fires first:
//   - a timer (MINTKEY_AUDIT_WAL_COMPACT_INTERVAL_SEC, default 300s)
//   - a WAL size threshold (MINTKEY_AUDIT_WAL_COMPACT_THRESHOLD_BYTES, default 64 MiB)
//
// Safety invariant: no undelivered event is ever dropped during compaction.
// Concurrent Enqueue calls during compaction are safe because appendWAL
// acquires walMu (the same mutex compaction holds for the read-filter-rename
// critical section).  Any line appended after compaction reads the snapshot
// but before it renames the temp file will simply be lost from the temp file,
// so we hold walMu for the entire read-filter-write-rename sequence.
//
// Source: #27 WAL rotation/compaction.
package auditq

import (
	"log/slog"
	"os"
	"strings"
	"time"
)

// CompactConfig controls the compaction trigger policy.
type CompactConfig struct {
	// IntervalSec is the maximum number of seconds between compaction passes.
	// 0 disables the timer trigger.
	IntervalSec int

	// ThresholdBytes is the WAL file size (bytes) that immediately triggers
	// compaction.  0 disables the threshold trigger.
	ThresholdBytes int64
}

// DefaultCompactConfig returns production defaults.
func DefaultCompactConfig() CompactConfig {
	return CompactConfig{
		IntervalSec:    300,      // 5 minutes
		ThresholdBytes: 64 << 20, // 64 MiB
	}
}

// compactWorker is the background goroutine that monitors WAL size and runs
// compaction when the timer or threshold fires.  It exits when stopCh is
// closed.
func (q *Queue) compactWorker(cfg CompactConfig) {
	if cfg.IntervalSec <= 0 && cfg.ThresholdBytes <= 0 {
		return // both triggers disabled; compaction is a no-op
	}

	var ticker *time.Ticker
	var tickCh <-chan time.Time

	if cfg.IntervalSec > 0 {
		ticker = time.NewTicker(time.Duration(cfg.IntervalSec) * time.Second)
		tickCh = ticker.C
		defer ticker.Stop()
	}

	for {
		var triggerReason string

		if cfg.ThresholdBytes > 0 {
			// Poll the WAL file size in a tight loop so large bursts compact
			// quickly without waiting a full timer interval.  We check every
			// second; this is a stat(2) syscall — negligible overhead.
			checkTicker := time.NewTicker(1 * time.Second)
		thresholdLoop:
			for {
				select {
				case <-checkTicker.C:
					if info, err := os.Stat(q.walPath); err == nil {
						q.metrics.walSizeBytes.Store(info.Size())
						if info.Size() >= cfg.ThresholdBytes {
							triggerReason = "threshold"
							break thresholdLoop
						}
					}
				case <-tickCh:
					triggerReason = "timer"
					break thresholdLoop
				case <-q.stopCh:
					checkTicker.Stop()
					return
				}
			}
			checkTicker.Stop()
		} else {
			// Threshold disabled — wait only on timer or stop.
			select {
			case <-tickCh:
				triggerReason = "timer"
			case <-q.stopCh:
				return
			}
		}

		q.compact(triggerReason)
	}
}

// compact performs one compaction pass: read WAL, filter to undelivered lines,
// atomic rename.  The entire operation holds walMu to prevent concurrent
// Enqueue from interleaving lines into the file mid-rename.
//
// Structured log on every compaction:
//
//	event=wal_compact trigger=<timer|threshold> wal_size_before=X size_after=Y
//	events_kept=N events_dropped=0
func (q *Queue) compact(triggerReason string) {
	q.walMu.Lock()
	defer q.walMu.Unlock()

	data, err := os.ReadFile(q.walPath)
	if err != nil {
		if os.IsNotExist(err) {
			return // nothing to compact
		}
		slog.Warn("auditq: compact: read WAL", "err", err)
		return
	}

	sizeBefore := int64(len(data))
	q.metrics.walSizeBytes.Store(sizeBefore)

	lines := strings.Split(string(data), "\n")
	kept := make([]string, 0, len(lines))
	eventsKept := 0
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue // skip blank lines between entries
		}
		if strings.HasPrefix(trimmed, walTombstone) {
			continue // skip tombstoned (delivered) lines
		}
		kept = append(kept, line)
		eventsKept++
	}

	// Rebuild file content; always end with a newline so the next Enqueue
	// appends cleanly.
	var newContent string
	if len(kept) > 0 {
		newContent = strings.Join(kept, "\n") + "\n"
	}
	sizeAfter := int64(len(newContent))

	// Write to a temp file next to the WAL, fsync, then atomic rename.
	tmpPath := q.walPath + ".compact.tmp"
	f, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		slog.Warn("auditq: compact: create temp file", "err", err)
		return
	}

	if _, err := f.WriteString(newContent); err != nil {
		f.Close()
		_ = os.Remove(tmpPath)
		slog.Warn("auditq: compact: write temp file", "err", err)
		return
	}
	if err := f.Sync(); err != nil {
		f.Close()
		_ = os.Remove(tmpPath)
		slog.Warn("auditq: compact: fsync temp file", "err", err)
		return
	}
	f.Close()

	if err := os.Rename(tmpPath, q.walPath); err != nil {
		_ = os.Remove(tmpPath)
		slog.Warn("auditq: compact: rename temp file", "err", err)
		return
	}

	// Update metrics.
	q.metrics.walSizeBytes.Store(sizeAfter)
	q.metrics.walPendingEvents.Store(int64(eventsKept))

	slog.Info("auditq: wal_compact",
		"event", "wal_compact",
		"trigger", triggerReason,
		"wal_size_before", sizeBefore,
		"size_after", sizeAfter,
		"events_kept", eventsKept,
		"events_dropped", 0, // INVARIANT: must always be 0
	)
}
