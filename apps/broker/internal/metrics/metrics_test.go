package metrics_test

import (
	"bytes"
	"strings"
	"sync"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/metrics"
)

// TestIncTokenIssued_Concurrent verifies that concurrent increments from many
// goroutines produce the correct final count.  1 000 increments across 10
// goroutines each doing 100 increments for the same (tenant, service) pair.
// A second pair is also exercised to confirm isolation between label sets.
func TestIncTokenIssued_Concurrent(t *testing.T) {
	const (
		goroutines   = 10
		perGoroutine = 100
		wantTotal    = goroutines * perGoroutine // 1 000
	)

	m := metrics.New()

	var wg sync.WaitGroup
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perGoroutine; j++ {
				m.IncTokenIssued("tenant_A", "svc_1")
			}
		}()
	}
	wg.Wait()

	// Also do a single increment on a second pair to confirm no cross-pollution.
	m.IncTokenIssued("tenant_B", "svc_2")

	var buf bytes.Buffer
	if err := m.WriteTo(&buf); err != nil {
		t.Fatalf("WriteTo: %v", err)
	}
	out := buf.String()

	// Verify the first pair hit exactly 1 000.
	wantLine := `mintkey_token_issued_total{tenant="tenant_A",service="svc_1"} 1000`
	if !strings.Contains(out, wantLine) {
		t.Errorf("expected line %q in output:\n%s", wantLine, out)
	}

	// Verify the second pair is 1, not affected by the first.
	wantLine2 := `mintkey_token_issued_total{tenant="tenant_B",service="svc_2"} 1`
	if !strings.Contains(out, wantLine2) {
		t.Errorf("expected line %q in output:\n%s", wantLine2, out)
	}
}

// TestWriteTo_ExpositionFormat verifies the exact Prometheus text format
// produced by WriteTo, including the HELP/TYPE headers.
func TestWriteTo_ExpositionFormat(t *testing.T) {
	m := metrics.New()
	m.IncTokenIssued("tenant_test", "svc_test")
	m.IncTokenIssued("tenant_test", "svc_test")
	m.IncTokenIssued("tenant_test", "svc_test")

	var buf bytes.Buffer
	if err := m.WriteTo(&buf); err != nil {
		t.Fatalf("WriteTo returned error: %v", err)
	}
	out := buf.String()

	wantLines := []string{
		"# HELP mintkey_token_issued_total Total tokens issued by the broker.",
		"# TYPE mintkey_token_issued_total counter",
		`mintkey_token_issued_total{tenant="tenant_test",service="svc_test"} 3`,
	}
	for _, want := range wantLines {
		if !strings.Contains(out, want) {
			t.Errorf("missing expected line:\n  want: %q\n   got:\n%s", want, out)
		}
	}
}

// TestWriteTo_NoCounters verifies that WriteTo on an empty Metrics still
// emits HELP and TYPE headers (so Prometheus sees the metric family).
func TestWriteTo_NoCounters(t *testing.T) {
	m := metrics.New()
	var buf bytes.Buffer
	if err := m.WriteTo(&buf); err != nil {
		t.Fatalf("WriteTo: %v", err)
	}
	out := buf.String()

	if !strings.Contains(out, "# HELP mintkey_token_issued_total") {
		t.Errorf("HELP header missing in empty output:\n%s", out)
	}
	if !strings.Contains(out, "# TYPE mintkey_token_issued_total counter") {
		t.Errorf("TYPE header missing in empty output:\n%s", out)
	}
}

// TestIncTokenIssued_LabelEscaping verifies that tenant/service IDs containing
// double-quote and backslash characters are safely escaped in the output.
func TestIncTokenIssued_LabelEscaping(t *testing.T) {
	m := metrics.New()
	m.IncTokenIssued(`ten"ant`, `svc\1`)

	var buf bytes.Buffer
	if err := m.WriteTo(&buf); err != nil {
		t.Fatalf("WriteTo: %v", err)
	}
	out := buf.String()

	// %q in Go renders `ten"ant` as `"ten\"ant"` and `svc\1` as `"svc\\1"`.
	wantTenant := `"ten\"ant"`
	wantService := `"svc\\1"`
	if !strings.Contains(out, wantTenant) {
		t.Errorf("escaped tenant not found; want %q in:\n%s", wantTenant, out)
	}
	if !strings.Contains(out, wantService) {
		t.Errorf("escaped service not found; want %q in:\n%s", wantService, out)
	}
}
