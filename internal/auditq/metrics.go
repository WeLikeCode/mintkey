// Package auditq — Prometheus-format metric gauges and counters for the audit
// queue.  Implemented with sync/atomic to avoid external dependencies; the
// MetricsHandler method emits the standard text exposition format (0.0.4) so
// Prometheus can scrape it directly.
//
// Source: #27 WAL rotation/compaction + dead-letter monitoring.
package auditq

import (
	"fmt"
	"io"
	"net/http"
	"sync/atomic"
)

// Metrics holds all Prometheus-format metrics for one Queue instance.
// All fields are updated via atomic operations so they are safe for concurrent
// reads (e.g., from an HTTP /metrics handler) and writes (from the drain and
// compact workers).
type Metrics struct {
	// deadLetterTotal is a counter: number of events moved to the dead-letter
	// file since process start.  Labels: service.
	deadLetterTotal atomic.Int64

	// deadLetterFileSizeBytes is a gauge: byte size of the dead-letter file,
	// updated after every dead-letter write and every compaction.
	deadLetterFileSizeBytes atomic.Int64

	// walSizeBytes is a gauge: byte size of the WAL file after the last
	// compaction (or Replay, whichever is most recent).
	walSizeBytes atomic.Int64

	// walPendingEvents is a gauge: number of undelivered events in the WAL
	// after the last compaction.
	walPendingEvents atomic.Int64

	// serviceLabel is the Prometheus label value for {service="..."}.
	serviceLabel string
}

// newMetrics creates a Metrics instance with the given service label.
func newMetrics(serviceLabel string) *Metrics {
	return &Metrics{serviceLabel: serviceLabel}
}

// MetricsHandler returns an http.HandlerFunc that writes all auditq metrics in
// Prometheus text exposition format (version 0.0.4).  Multiple Queue instances
// can register themselves on the same http.ServeMux by calling this on each.
func (m *Metrics) MetricsHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
		writeMetrics(w, m)
	}
}

// writeMetrics writes all auditq metrics for m to w.
func writeMetrics(w io.Writer, m *Metrics) {
	svc := m.serviceLabel

	// auditq_dead_letter_events_total
	fmt.Fprintf(w,
		"# HELP auditq_dead_letter_events_total Total number of audit events moved to the dead-letter file.\n"+
			"# TYPE auditq_dead_letter_events_total counter\n"+
			"auditq_dead_letter_events_total{service=%q} %d\n",
		svc, m.deadLetterTotal.Load(),
	)

	// auditq_dead_letter_file_size_bytes
	fmt.Fprintf(w,
		"# HELP auditq_dead_letter_file_size_bytes Current byte size of the dead-letter file.\n"+
			"# TYPE auditq_dead_letter_file_size_bytes gauge\n"+
			"auditq_dead_letter_file_size_bytes{service=%q} %d\n",
		svc, m.deadLetterFileSizeBytes.Load(),
	)

	// auditq_wal_size_bytes
	fmt.Fprintf(w,
		"# HELP auditq_wal_size_bytes Current byte size of the WAL file.\n"+
			"# TYPE auditq_wal_size_bytes gauge\n"+
			"auditq_wal_size_bytes{service=%q} %d\n",
		svc, m.walSizeBytes.Load(),
	)

	// auditq_wal_pending_events
	fmt.Fprintf(w,
		"# HELP auditq_wal_pending_events Number of undelivered events in the WAL after last compaction.\n"+
			"# TYPE auditq_wal_pending_events gauge\n"+
			"auditq_wal_pending_events{service=%q} %d\n",
		svc, m.walPendingEvents.Load(),
	)
}

// WriteMetricsTo writes all auditq metrics for q to w in Prometheus text
// exposition format.  Call this from an existing /metrics handler to merge
// auditq metrics alongside other service metrics.
func (q *Queue) WriteMetricsTo(w io.Writer) {
	writeMetrics(w, q.metrics)
}
