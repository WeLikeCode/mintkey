package issue_test

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/api/issue"
	"github.com/mintkey/mintkey/services/broker/internal/issuer"
	"github.com/mintkey/mintkey/services/broker/internal/keys"
)

const testMCPToken = "test-mcp-service-token"

func newTestHandler(t *testing.T) http.Handler {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ring := keys.NewKeyRing()
	ring.Add("kid_01TESTISSUEID0000000000000", pub)
	iss := issuer.New(priv, "kid_01TESTISSUEID0000000000000", ring)
	return issue.NewHandler(iss, testMCPToken)
}

// TestIssue_ValidRequest_Returns200WithJWT asserts that a valid request with
// correct token returns 200 and a 3-part dot-separated JWT.
// Sources: ADR-0006; T-1.6.x.
func TestIssue_ValidRequest_Returns200WithJWT(t *testing.T) {
	h := newTestHandler(t)

	body := map[string]any{
		"agent_id":    "agent_01HZ0000000000000000000001",
		"service_id":  "svc_01HZ0000000000000000000002",
		"tenant_id":   "tenant_01HZ0000000000000000000003",
		"scope":       "read",
		"ttl_seconds": 300,
	}
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/v1/issue", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", testMCPToken)

	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body: %s", w.Code, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}

	token, ok := resp["token"].(string)
	if !ok || token == "" {
		t.Fatalf("token missing or empty in response: %v", resp)
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Errorf("token = %q: want 3 dot-separated base64url parts, got %d", token, len(parts))
	}
	if _, ok := resp["expires_at"].(float64); !ok {
		t.Errorf("expires_at missing or wrong type in response: %v", resp)
	}
}

// TestIssue_MissingOrWrongToken_Returns401 asserts that missing or wrong
// X-Mintkey-Service-Token is rejected with 401.
// Sources: ADR-0018 §3; T-1.6.x.
func TestIssue_MissingOrWrongToken_Returns401(t *testing.T) {
	h := newTestHandler(t)

	body := map[string]any{
		"agent_id":    "agent_01HZ0000000000000000000001",
		"service_id":  "svc_01HZ0000000000000000000002",
		"tenant_id":   "tenant_01HZ0000000000000000000003",
		"scope":       "read",
		"ttl_seconds": 300,
	}
	b, _ := json.Marshal(body)

	cases := []struct {
		name  string
		token string
	}{
		{"missing", ""},
		{"wrong", "wrong-token"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/v1/issue", bytes.NewReader(b))
			req.Header.Set("Content-Type", "application/json")
			if tc.token != "" {
				req.Header.Set("X-Mintkey-Service-Token", tc.token)
			}
			w := httptest.NewRecorder()
			h.ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Errorf("status = %d, want 401", w.Code)
			}
		})
	}
}

// TestIssue_TTLTooLarge_Returns400 asserts that ttl_seconds > 3600 is rejected
// with 400.
// Sources: T-1.6.x.
func TestIssue_TTLTooLarge_Returns400(t *testing.T) {
	h := newTestHandler(t)

	body := map[string]any{
		"agent_id":    "agent_01HZ0000000000000000000001",
		"service_id":  "svc_01HZ0000000000000000000002",
		"tenant_id":   "tenant_01HZ0000000000000000000003",
		"scope":       "read",
		"ttl_seconds": 3601,
	}
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/v1/issue", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", testMCPToken)

	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", w.Code)
	}
}
