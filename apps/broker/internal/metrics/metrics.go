// Package metrics implements Prometheus-format token-issued counters for the
// broker.  Implemented with sync/atomic + sync.Map to avoid external
// dependencies; the WriteTo method emits the standard text exposition format
// (0.0.4) so Prometheus can scrape it directly.
//
// Design: same sync/atomic pattern as internal/auditq/metrics.go (OPS-O).
// Counters are keyed on "tenant|service" and stored as *atomic.Int64 values
// inside a sync.Map, so new label combinations are created on first use and
// all increments are race-free without a global mutex.
package metrics

import (
	"fmt"
	"io"
	"strings"
	"sync"
	"sync/atomic"
)

// Metrics holds all Prometheus-format broker metrics.
// The zero value is not usable — use New().
type Metrics struct {
	// tokenIssued maps "tenantID|serviceID" → *atomic.Int64 counter.
	// sync.Map is safe for concurrent reads and writes from multiple goroutines.
	tokenIssued sync.Map
}

// New returns a ready-to-use *Metrics.
func New() *Metrics {
	return &Metrics{}
}

// IncTokenIssued atomically increments the mintkey_token_issued_total counter
// for the given tenant/service pair.  It creates the counter on the first call
// for a previously unseen (tenantID, serviceID) combination.
func (m *Metrics) IncTokenIssued(tenantID, serviceID string) {
	key := tenantID + "|" + serviceID
	val, _ := m.tokenIssued.LoadOrStore(key, &atomic.Int64{})
	val.(*atomic.Int64).Add(1)
}

// WriteTo writes all broker metrics to w in Prometheus text exposition format
// (version 0.0.4).  It emits the HELP and TYPE headers once, then one sample
// line per observed (tenant, service) pair.  Call this from an existing
// /metrics handler to merge broker metrics alongside other service metrics.
//
// Label values are rendered with %q (Go quoted string), which produces the
// required double-quoted, backslash-escaped form — identical to the pattern
// used in internal/auditq/metrics.go.
//
// Returns the first error encountered by the underlying writer; on partial
// writes the caller should discard or close the response.
func (m *Metrics) WriteTo(w io.Writer) error {
	// Collect all counters into a local slice so we can emit HELP/TYPE once
	// before iterating, which is required by exposition format 0.0.4.
	type sample struct {
		tenant  string
		service string
		value   int64
	}
	var samples []sample

	m.tokenIssued.Range(func(rawKey, rawVal any) bool {
		key := rawKey.(string)
		parts := strings.SplitN(key, "|", 2)
		if len(parts) != 2 {
			return true // skip malformed keys (should never happen)
		}
		samples = append(samples, sample{
			tenant:  parts[0],
			service: parts[1],
			value:   rawVal.(*atomic.Int64).Load(),
		})
		return true
	})

	if _, err := fmt.Fprint(w,
		"# HELP mintkey_token_issued_total Total tokens issued by the broker.\n"+
			"# TYPE mintkey_token_issued_total counter\n",
	); err != nil {
		return err
	}

	for _, s := range samples {
		// %q produces "value" with backslash-escaping — valid Prometheus label
		// value syntax matching the auditq pattern.
		if _, err := fmt.Fprintf(w,
			"mintkey_token_issued_total{tenant=%q,service=%q} %d\n",
			s.tenant,
			s.service,
			s.value,
		); err != nil {
			return err
		}
	}
	return nil
}
