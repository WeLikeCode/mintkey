package metrics

import (
	"strings"
	"sync"
	"testing"
)

// loadInt64 is a helper that extracts a Load() value from a *atomic.Int64
// stored in a sync.Map without importing sync/atomic in the test file.
type int64Loader interface{ Load() int64 }

// TestIncProxyHit_SingleService verifies the counter increments for one service.
func TestIncProxyHit_SingleService(t *testing.T) {
	m := New()
	m.IncProxyHit("svc-a")
	m.IncProxyHit("svc-a")
	m.IncProxyHit("svc-a")

	v, ok := m.hits.Load("svc-a")
	if !ok {
		t.Fatal("expected svc-a to be present")
	}
	if got := v.(int64Loader).Load(); got != 3 {
		t.Fatalf("IncProxyHit: want 3, got %d", got)
	}
}

// TestIncProxyHit_Concurrent runs concurrent hits and verifies the final count.
func TestIncProxyHit_Concurrent(t *testing.T) {
	m := New()
	const n = 1000
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			m.IncProxyHit("svc-concurrent")
		}()
	}
	wg.Wait()

	v, ok := m.hits.Load("svc-concurrent")
	if !ok {
		t.Fatal("key missing")
	}
	got := v.(interface{ Load() int64 }).Load()
	if got != n {
		t.Fatalf("concurrent IncProxyHit: want %d, got %d", n, got)
	}
}

// TestIncProxyDenied verifies multiple reasons are tracked separately.
func TestIncProxyDenied(t *testing.T) {
	m := New()
	m.IncProxyDenied("svc-x", "unauthenticated")
	m.IncProxyDenied("svc-x", "unauthenticated")
	m.IncProxyDenied("svc-x", "rate_limited")

	check := func(key string, want int64) {
		t.Helper()
		v, ok := m.denied.Load(key)
		if !ok {
			t.Fatalf("key %q missing", key)
		}
		got := v.(interface{ Load() int64 }).Load()
		if got != want {
			t.Fatalf("key %q: want %d, got %d", key, want, got)
		}
	}
	check("svc-x|unauthenticated", 2)
	check("svc-x|rate_limited", 1)
}

// TestObserveAddedLatency_BucketInclusion verifies that observing 0.07 s
// increments bucket 0.1 and all higher buckets (including +Inf) but NOT 0.05.
func TestObserveAddedLatency_BucketInclusion(t *testing.T) {
	m := New()
	m.ObserveAddedLatency("svc-b", 0.07)

	bsv, ok := m.latencyBuckets.Load("svc-b")
	if !ok {
		t.Fatal("bucket series missing")
	}
	bs := bsv.(*bucketSeries)

	// Boundaries: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5]
	// Indices:       0      1      2     3      4     5    6     7   8    9   10
	// +Inf at index 11
	// 0.07 > 0.05 (idx 4), so first bucket ≥ 0.07 is 0.1 (idx 5).
	// Indices 5..11 must be 1; 0..4 must be 0.

	for i := 0; i <= 4; i++ {
		if got := bs.counts[i].Load(); got != 0 {
			t.Errorf("bucket[%d] (le=%.3f): want 0, got %d", i, bucketBoundaries[i], got)
		}
	}
	for i := 5; i <= numBuckets; i++ {
		if got := bs.counts[i].Load(); got != 1 {
			leStr := "+Inf"
			if i < numBuckets {
				leStr = formatLE(bucketBoundaries[i])
			}
			t.Errorf("bucket[%d] (le=%s): want 1, got %d", i, leStr, got)
		}
	}
}

// TestObserveAddedLatency_BelowAllBuckets verifies a very small value hits
// bucket index 0 and all higher.
func TestObserveAddedLatency_BelowAllBuckets(t *testing.T) {
	m := New()
	m.ObserveAddedLatency("svc-tiny", 0.0001)

	bsv, _ := m.latencyBuckets.Load("svc-tiny")
	bs := bsv.(*bucketSeries)
	for i := 0; i <= numBuckets; i++ {
		if got := bs.counts[i].Load(); got != 1 {
			t.Errorf("bucket[%d]: want 1, got %d", i, got)
		}
	}
}

// TestObserveAddedLatency_AboveAllBuckets verifies a huge value only hits +Inf.
func TestObserveAddedLatency_AboveAllBuckets(t *testing.T) {
	m := New()
	m.ObserveAddedLatency("svc-huge", 999.0)

	bsv, _ := m.latencyBuckets.Load("svc-huge")
	bs := bsv.(*bucketSeries)
	for i := 0; i < numBuckets; i++ {
		if got := bs.counts[i].Load(); got != 0 {
			t.Errorf("finite bucket[%d]: want 0, got %d", i, got)
		}
	}
	if got := bs.counts[numBuckets].Load(); got != 1 {
		t.Errorf("+Inf bucket: want 1, got %d", got)
	}
}

// TestObserveAddedLatency_SumAndCount verifies _sum and _count are tracked.
func TestObserveAddedLatency_SumAndCount(t *testing.T) {
	m := New()
	m.ObserveAddedLatency("svc-sc", 0.1)
	m.ObserveAddedLatency("svc-sc", 0.2)
	m.ObserveAddedLatency("svc-sc", 0.3)

	// Count.
	cv, _ := m.latencyCount.Load("svc-sc")
	if count := cv.(interface{ Load() int64 }).Load(); count != 3 {
		t.Errorf("count: want 3, got %d", count)
	}
	// Sum in nanos: 0.1+0.2+0.3 = 0.6 s = 600_000_000 ns (within rounding).
	sv, _ := m.latencySum.Load("svc-sc")
	sumNanos := sv.(interface{ Load() uint64 }).Load()
	const want = uint64(600_000_000)
	// Allow ±1000 ns rounding.
	if sumNanos < want-1000 || sumNanos > want+1000 {
		t.Errorf("sum nanos: want ~%d, got %d", want, sumNanos)
	}
}

// TestObserveAddedLatency_Concurrent runs concurrent observations and verifies
// that _count equals the number of goroutines (no lost updates).
func TestObserveAddedLatency_Concurrent(t *testing.T) {
	m := New()
	const n = 500
	var wg sync.WaitGroup
	wg.Add(n)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			m.ObserveAddedLatency("svc-lat-concurrent", 0.05)
		}()
	}
	wg.Wait()

	cv, _ := m.latencyCount.Load("svc-lat-concurrent")
	if count := cv.(interface{ Load() int64 }).Load(); count != n {
		t.Fatalf("concurrent ObserveAddedLatency count: want %d, got %d", n, count)
	}
}

// TestConcurrentHitAndLatency runs concurrent IncProxyHit + ObserveAddedLatency
// to exercise the race detector.
func TestConcurrentHitAndLatency(t *testing.T) {
	m := New()
	const n = 200
	var wg sync.WaitGroup
	wg.Add(n * 2)
	for i := 0; i < n; i++ {
		go func() {
			defer wg.Done()
			m.IncProxyHit("svc-race")
		}()
		go func() {
			defer wg.Done()
			m.ObserveAddedLatency("svc-race", 0.03)
		}()
	}
	wg.Wait()
}

// TestWriteTo_ContainsAllFamilies verifies the exposition contains _bucket,
// _sum, _count, hit_total, and denied_total lines.
func TestWriteTo_ContainsAllFamilies(t *testing.T) {
	m := New()
	m.IncProxyHit("svc-write")
	m.IncProxyHit("svc-write")
	m.IncProxyDenied("svc-write", "unauthenticated")
	m.ObserveAddedLatency("svc-write", 0.07)

	var sb strings.Builder
	if err := m.WriteTo(&sb); err != nil {
		t.Fatalf("WriteTo: %v", err)
	}
	out := sb.String()

	mustContain := []string{
		"mintkey_proxy_hit_total",
		"mintkey_proxy_denied_total",
		"mintkey_proxy_added_latency_seconds_bucket",
		"mintkey_proxy_added_latency_seconds_sum",
		"mintkey_proxy_added_latency_seconds_count",
		`le="+Inf"`,
		`reason="unauthenticated"`,
		`service="svc-write"`,
	}
	for _, want := range mustContain {
		if !strings.Contains(out, want) {
			t.Errorf("WriteTo output missing %q\nFull output:\n%s", want, out)
		}
	}
}

// TestWriteTo_HitCountCorrect verifies the counter value in exposition.
func TestWriteTo_HitCountCorrect(t *testing.T) {
	m := New()
	for i := 0; i < 5; i++ {
		m.IncProxyHit("svc-count")
	}
	var sb strings.Builder
	_ = m.WriteTo(&sb)
	out := sb.String()

	// Expect: mintkey_proxy_hit_total{service="svc-count"} 5
	want := `mintkey_proxy_hit_total{service="svc-count"} 5`
	if !strings.Contains(out, want) {
		t.Errorf("expected %q in output:\n%s", want, out)
	}
}

// TestWriteTo_BucketZeroForSmallValues verifies that after observing 0.07s,
// the 0.001 bucket line shows 0 (not incremented).
func TestWriteTo_BucketZeroForSmallValues(t *testing.T) {
	m := New()
	m.ObserveAddedLatency("svc-z", 0.07)

	var sb strings.Builder
	_ = m.WriteTo(&sb)
	out := sb.String()

	// The 0.001 bucket should be 0 since 0.07 > 0.001.
	want := `mintkey_proxy_added_latency_seconds_bucket{service="svc-z",le="0.001"} 0`
	if !strings.Contains(out, want) {
		t.Errorf("expected bucket le=0.001 to be 0:\n%s", out)
	}

	// The 0.1 bucket should be 1.
	want2 := `mintkey_proxy_added_latency_seconds_bucket{service="svc-z",le="0.1"} 1`
	if !strings.Contains(out, want2) {
		t.Errorf("expected bucket le=0.1 to be 1:\n%s", out)
	}
}

// TestWriteTo_EmptyMetrics verifies that an empty Metrics writes valid headers
// but no data lines.
func TestWriteTo_EmptyMetrics(t *testing.T) {
	m := New()
	var sb strings.Builder
	if err := m.WriteTo(&sb); err != nil {
		t.Fatalf("WriteTo on empty metrics: %v", err)
	}
	out := sb.String()
	if !strings.Contains(out, "# HELP mintkey_proxy_hit_total") {
		t.Error("missing HELP header for hit_total")
	}
}
