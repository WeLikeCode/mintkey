// Package metrics — Prometheus-format counters and histograms for the proxy
// plugin.  Implemented with sync/atomic to avoid the prometheus/client_golang
// dependency.  Exposes the text exposition format 0.0.4 so Prometheus can
// scrape it directly.
//
// Source: OPS-P; design §10 proxy metrics.
package metrics

import (
	"fmt"
	"io"
	"math"
	"sort"
	"sync"
	"sync/atomic"
)

// bucketBoundaries are the upper bounds for the added-latency histogram in
// seconds.  These match the Grafana dashboard queries.
var bucketBoundaries = []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5}

const numBuckets = 11 // len(bucketBoundaries); 11 finite buckets + 1 +Inf = 12 total

// bucketSeries holds one atomic counter per finite bucket plus a +Inf bucket.
// Prometheus cumulative convention: each counter represents observations ≤ le,
// so observing a value increments the bucket for that boundary and all higher.
type bucketSeries struct {
	counts [numBuckets + 1]atomic.Int64 // indices 0‥10 → finite; index 11 → +Inf
}

// Metrics holds all Prometheus-format metrics for the proxy plugin.
// All fields are updated via atomic operations so they are safe for concurrent
// access by the request handler and the /metrics scrape handler.
type Metrics struct {
	// hits: keyed on serviceID → *atomic.Int64
	hits sync.Map

	// denied: keyed on "serviceID|reason" → *atomic.Int64
	denied sync.Map

	// latencyBuckets: keyed on serviceID → *bucketSeries
	latencyBuckets sync.Map

	// latencySum: keyed on serviceID → *atomic.Uint64 (sum in nanoseconds)
	latencySum sync.Map

	// latencyCount: keyed on serviceID → *atomic.Int64
	latencyCount sync.Map
}

// New creates a ready-to-use Metrics instance.
func New() *Metrics {
	return &Metrics{}
}

// IncProxyHit records one successful proxy hit for serviceID.
func (m *Metrics) IncProxyHit(serviceID string) {
	c := loadOrStoreInt64(&m.hits, serviceID)
	c.Add(1)
}

// IncProxyDenied records one proxy denial for serviceID with the given reason.
// Valid reasons: unauthenticated, permission_denied, rate_limited, revoked,
// backend_error.
func (m *Metrics) IncProxyDenied(serviceID, reason string) {
	key := serviceID + "|" + reason
	c := loadOrStoreInt64(&m.denied, key)
	c.Add(1)
}

// ObserveAddedLatency records a plugin-added latency observation (seconds).
// It finds the smallest bucket boundary ≥ seconds and increments that bucket
// plus all higher buckets (Prometheus cumulative convention).  The sum is
// accumulated in nanoseconds and converted to seconds on exposition.
func (m *Metrics) ObserveAddedLatency(serviceID string, seconds float64) {
	bs := loadOrStoreBucketSeries(&m.latencyBuckets, serviceID)

	// Find the first bucket boundary ≥ seconds.  Increment that bucket and all
	// higher buckets (cumulative histogram).
	incremented := false
	for i, le := range bucketBoundaries {
		if seconds <= le {
			if !incremented {
				// Increment from this index onwards through +Inf.
				for j := i; j <= numBuckets; j++ {
					bs.counts[j].Add(1)
				}
				incremented = true
				break
			}
		}
	}
	if !incremented {
		// Value exceeds all finite boundaries — only +Inf gets incremented.
		bs.counts[numBuckets].Add(1)
	}

	// Accumulate sum (store nanoseconds as uint64 to avoid float race).
	nanos := uint64(seconds * 1e9)
	sum := loadOrStoreUint64(&m.latencySum, serviceID)
	sum.Add(nanos)

	cnt := loadOrStoreInt64(&m.latencyCount, serviceID)
	cnt.Add(1)
}

// WriteTo writes all proxy metrics to w in Prometheus text exposition format
// (version 0.0.4).  Call this from the /metrics handler alongside other
// metric writers (e.g. auditq.WriteMetricsTo).
func (m *Metrics) WriteMetricsTo(w io.Writer) error {
	// Collect all serviceIDs seen by hits, denied, or latency.
	svcSet := make(map[string]struct{})
	m.hits.Range(func(k, _ any) bool { svcSet[k.(string)] = struct{}{}; return true })
	m.latencyBuckets.Range(func(k, _ any) bool { svcSet[k.(string)] = struct{}{}; return true })

	// Build a sorted list for deterministic output.
	svcs := make([]string, 0, len(svcSet))
	for s := range svcSet {
		svcs = append(svcs, s)
	}
	sort.Strings(svcs)

	// --- mintkey_proxy_hit_total ---
	if _, err := fmt.Fprintf(w,
		"# HELP mintkey_proxy_hit_total Total successful proxy hits.\n"+
			"# TYPE mintkey_proxy_hit_total counter\n",
	); err != nil {
		return err
	}
	for _, svc := range svcs {
		if v, ok := m.hits.Load(svc); ok {
			c := v.(*atomic.Int64)
			if _, err := fmt.Fprintf(w, "mintkey_proxy_hit_total{service=%q} %d\n", svc, c.Load()); err != nil {
				return err
			}
		}
	}

	// --- mintkey_proxy_denied_total ---
	if _, err := fmt.Fprintf(w,
		"# HELP mintkey_proxy_denied_total Total proxy denials.\n"+
			"# TYPE mintkey_proxy_denied_total counter\n",
	); err != nil {
		return err
	}
	// Collect denied entries, sorted.
	type deniedEntry struct{ key, svc, reason string }
	var deniedEntries []deniedEntry
	m.denied.Range(func(k, _ any) bool {
		key := k.(string)
		svc, reason := splitDeniedKey(key)
		deniedEntries = append(deniedEntries, deniedEntry{key, svc, reason})
		return true
	})
	sort.Slice(deniedEntries, func(i, j int) bool {
		if deniedEntries[i].svc != deniedEntries[j].svc {
			return deniedEntries[i].svc < deniedEntries[j].svc
		}
		return deniedEntries[i].reason < deniedEntries[j].reason
	})
	for _, e := range deniedEntries {
		if v, ok := m.denied.Load(e.key); ok {
			c := v.(*atomic.Int64)
			if _, err := fmt.Fprintf(w, "mintkey_proxy_denied_total{service=%q,reason=%q} %d\n",
				e.svc, e.reason, c.Load()); err != nil {
				return err
			}
		}
	}

	// --- mintkey_proxy_added_latency_seconds ---
	if _, err := fmt.Fprintf(w,
		"# HELP mintkey_proxy_added_latency_seconds Plugin-added latency.\n"+
			"# TYPE mintkey_proxy_added_latency_seconds histogram\n",
	); err != nil {
		return err
	}
	for _, svc := range svcs {
		bsv, ok := m.latencyBuckets.Load(svc)
		if !ok {
			continue
		}
		bs := bsv.(*bucketSeries)
		// Finite buckets.
		for i, le := range bucketBoundaries {
			leStr := formatLE(le)
			if _, err := fmt.Fprintf(w, "mintkey_proxy_added_latency_seconds_bucket{service=%q,le=%q} %d\n",
				svc, leStr, bs.counts[i].Load()); err != nil {
				return err
			}
		}
		// +Inf bucket.
		if _, err := fmt.Fprintf(w, "mintkey_proxy_added_latency_seconds_bucket{service=%q,le=\"+Inf\"} %d\n",
			svc, bs.counts[numBuckets].Load()); err != nil {
			return err
		}
		// _sum (convert nanoseconds back to seconds).
		sumNanos := uint64(0)
		if sv, ok2 := m.latencySum.Load(svc); ok2 {
			sumNanos = sv.(*atomic.Uint64).Load()
		}
		sumSecs := float64(sumNanos) / 1e9
		if _, err := fmt.Fprintf(w, "mintkey_proxy_added_latency_seconds_sum{service=%q} %g\n",
			svc, sumSecs); err != nil {
			return err
		}
		// _count.
		countVal := int64(0)
		if cv, ok2 := m.latencyCount.Load(svc); ok2 {
			countVal = cv.(*atomic.Int64).Load()
		}
		if _, err := fmt.Fprintf(w, "mintkey_proxy_added_latency_seconds_count{service=%q} %d\n",
			svc, countVal); err != nil {
			return err
		}
	}
	return nil
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

// loadOrStoreInt64 returns the existing *atomic.Int64 for key in m, or stores
// and returns a new zero-valued one.
func loadOrStoreInt64(m *sync.Map, key string) *atomic.Int64 {
	v, _ := m.LoadOrStore(key, new(atomic.Int64))
	return v.(*atomic.Int64)
}

// loadOrStoreUint64 returns the existing *atomic.Uint64 for key in m, or
// stores and returns a new zero-valued one.
func loadOrStoreUint64(m *sync.Map, key string) *atomic.Uint64 {
	v, _ := m.LoadOrStore(key, new(atomic.Uint64))
	return v.(*atomic.Uint64)
}

// loadOrStoreBucketSeries returns the existing *bucketSeries for key, or
// stores and returns a new zero-valued one.
func loadOrStoreBucketSeries(m *sync.Map, key string) *bucketSeries {
	v, _ := m.LoadOrStore(key, new(bucketSeries))
	return v.(*bucketSeries)
}

// splitDeniedKey splits a "serviceID|reason" key into its two parts.
func splitDeniedKey(key string) (svc, reason string) {
	for i := 0; i < len(key); i++ {
		if key[i] == '|' {
			return key[:i], key[i+1:]
		}
	}
	return key, ""
}

// formatLE converts a float64 bucket boundary to its canonical label string,
// matching the values the Grafana dashboard queries.
func formatLE(le float64) string {
	// Use the shortest unambiguous decimal representation that round-trips.
	if le == math.Trunc(le) {
		return fmt.Sprintf("%g", le)
	}
	return fmt.Sprintf("%g", le)
}
