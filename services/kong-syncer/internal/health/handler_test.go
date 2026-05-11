// Tests for the Kong-syncer health endpoint.
//
// Source: design §9; T-1.0.6.
package health_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/mintkey/mintkey/services/kong-syncer/internal/health"
)

// TestHealth_Returns200 asserts GET /v1/health → 200 {"status":"ok"}.
// Source: T-1.0.6 acceptance.
func TestHealth_Returns200(t *testing.T) {
	h := health.Handler()

	req := httptest.NewRequest(http.MethodGet, "/v1/health", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}

	ct := rec.Header().Get("Content-Type")
	if ct != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}

	var body struct {
		Status string `json:"status"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal body: %v", err)
	}
	if body.Status != "ok" {
		t.Errorf("status = %q, want ok", body.Status)
	}
}
