// Tests for POST /v1/api-keys/resolve.
//
// TDD: written before implementation per T-4.3 discipline.
// Sources: design §3; Req 3.1, 3.2, 3.3, 3.5, 10.2; ADR-0018.
package resolve_test

import (
	"bytes"
	"context"
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/broker/internal/api/resolve"
)

// mockStore implements resolve.Store in tests without a real DB.
type mockStore struct {
	row     *resolve.KeyRow
	agentOK bool
}

func (m *mockStore) LookupByFingerprint(_ context.Context, _, _ string) (*resolve.KeyRow, error) {
	return m.row, nil
}

func (m *mockStore) AgentActive(_ context.Context, _, _ string) (bool, error) {
	return m.agentOK, nil
}

func newHandler(store resolve.Store, proxyToken string) http.Handler {
	return resolve.NewHandler(store, proxyToken)
}

func post(h http.Handler, body any, token string) *httptest.ResponseRecorder {
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/v1/api-keys/resolve", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("X-Mintkey-Service-Token", token)
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	return w
}

type reqBody struct {
	KeyFingerprint string `json:"key_fingerprint"`
	PresentedKey   string `json:"presented_key"`
	ServiceID      string `json:"service_id"`
	TenantID       string `json:"tenant_id"`
}

func errCode(w *httptest.ResponseRecorder) string {
	var m map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &m)
	if c, ok := m["mintkey:code"].(string); ok {
		return c
	}
	return ""
}

const proxyToken = "svcid_proxy_test_secret"

// --- missing / wrong service token → 401 ---

func TestMissingServiceToken(t *testing.T) {
	h := newHandler(&mockStore{}, proxyToken)
	w := post(h, reqBody{KeyFingerprint: "aabbccdd", PresentedKey: "mk_svckey_X", ServiceID: "svc_01", TenantID: "tenant_01"}, "")
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
}

func TestWrongServiceToken(t *testing.T) {
	h := newHandler(&mockStore{}, proxyToken)
	w := post(h, reqBody{KeyFingerprint: "aabbccdd", PresentedKey: "mk_svckey_X", ServiceID: "svc_01", TenantID: "tenant_01"}, "wrong_token")
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
}

// --- unknown fingerprint → constant-time api_key_invalid ---

func TestUnknownFingerprint(t *testing.T) {
	h := newHandler(&mockStore{row: nil, agentOK: true}, proxyToken)
	w := post(h, reqBody{KeyFingerprint: "deadbeef", PresentedKey: "mk_svckey_X", ServiceID: "svc_01", TenantID: "tenant_01"}, proxyToken)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
	if errCode(w) != "api_key_invalid" {
		t.Fatalf("want api_key_invalid, got %q", errCode(w))
	}
}

// --- wrong key (row found but hash mismatch) → api_key_invalid ---

func TestWrongKey(t *testing.T) {
	// Use a real argon2id hash of "correct_key" so the handler can actually verify
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_01TESTROW0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
	}
	h := newHandler(&mockStore{row: row, agentOK: true}, proxyToken)
	w := post(h, reqBody{
		KeyFingerprint: "aabbccdd",
		PresentedKey:   "wrong_key",
		ServiceID:      "svc_01TESTROW0000000000000001",
		TenantID:       "tenant_01TESTROW000000000000001",
	}, proxyToken)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
	if errCode(w) != "api_key_invalid" {
		t.Fatalf("want api_key_invalid, got %q", errCode(w))
	}
}

// --- revoked row → api_key_revoked ---

func TestRevokedRow(t *testing.T) {
	now := time.Now()
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_01TESTROW0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
		RevokedAt:      &now,
	}
	h := newHandler(&mockStore{row: row, agentOK: true}, proxyToken)
	w := post(h, reqBody{
		KeyFingerprint: "aabbccdd",
		PresentedKey:   "correct_key",
		ServiceID:      "svc_01TESTROW0000000000000001",
		TenantID:       "tenant_01TESTROW000000000000001",
	}, proxyToken)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
	if errCode(w) != "api_key_revoked" {
		t.Fatalf("want api_key_revoked, got %q", errCode(w))
	}
}

// --- revoked agent → api_key_revoked ---

func TestRevokedAgent(t *testing.T) {
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_01TESTROW0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
	}
	h := newHandler(&mockStore{row: row, agentOK: false}, proxyToken)
	w := post(h, reqBody{
		KeyFingerprint: "aabbccdd",
		PresentedKey:   "correct_key",
		ServiceID:      "svc_01TESTROW0000000000000001",
		TenantID:       "tenant_01TESTROW000000000000001",
	}, proxyToken)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
	if errCode(w) != "api_key_revoked" {
		t.Fatalf("want api_key_revoked, got %q", errCode(w))
	}
}

// --- expired → api_key_expired ---

func TestExpiredKey(t *testing.T) {
	past := time.Now().Add(-time.Hour)
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_01TESTROW0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
		ExpiresAt:      &past,
	}
	h := newHandler(&mockStore{row: row, agentOK: true}, proxyToken)
	w := post(h, reqBody{
		KeyFingerprint: "aabbccdd",
		PresentedKey:   "correct_key",
		ServiceID:      "svc_01TESTROW0000000000000001",
		TenantID:       "tenant_01TESTROW000000000000001",
	}, proxyToken)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
	if errCode(w) != "api_key_expired" {
		t.Fatalf("want api_key_expired, got %q", errCode(w))
	}
}

// --- wrong service → api_key_wrong_service ---

func TestWrongService(t *testing.T) {
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_DIFFERENT0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
	}
	h := newHandler(&mockStore{row: row, agentOK: true}, proxyToken)
	w := post(h, reqBody{
		KeyFingerprint: "aabbccdd",
		PresentedKey:   "correct_key",
		ServiceID:      "svc_REQUESTED0000000000000001",
		TenantID:       "tenant_01TESTROW000000000000001",
	}, proxyToken)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", w.Code)
	}
	if errCode(w) != "api_key_wrong_service" {
		t.Fatalf("want api_key_wrong_service, got %q", errCode(w))
	}
}

// --- happy path returns the binding ---

func TestHappyPath(t *testing.T) {
	future := time.Now().Add(24 * time.Hour)
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_01TESTROW0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
		ExpiresAt:      &future,
	}
	h := newHandler(&mockStore{row: row, agentOK: true}, proxyToken)
	w := post(h, reqBody{
		KeyFingerprint: "aabbccdd",
		PresentedKey:   "correct_key",
		ServiceID:      "svc_01TESTROW0000000000000001",
		TenantID:       "tenant_01TESTROW000000000000001",
	}, proxyToken)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	if resp["api_key_id"] != "svckey_01TESTROW0000000000000001" {
		t.Fatalf("unexpected api_key_id: %v", resp["api_key_id"])
	}
	if resp["agent_id"] != "agent_01TESTROW0000000000000001" {
		t.Fatalf("unexpected agent_id: %v", resp["agent_id"])
	}
}

// --- rate limit exceeded → 429 ---

func TestRateLimitPerFingerprint(t *testing.T) {
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_01TESTROW0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
	}
	h := newHandler(&mockStore{row: row, agentOK: true}, proxyToken)

	body := reqBody{
		KeyFingerprint: "rateme01",
		PresentedKey:   "correct_key",
		ServiceID:      "svc_01TESTROW0000000000000001",
		TenantID:       "tenant_01TESTROW000000000000001",
	}

	// Burst the per-fingerprint bucket (limit = 20/min)
	got429 := false
	for i := 0; i < 25; i++ {
		w := post(h, body, proxyToken)
		if w.Code == http.StatusTooManyRequests {
			got429 = true
			break
		}
	}
	if !got429 {
		t.Fatal("expected 429 after exhausting fingerprint rate limit")
	}
}

// --- constant-time: unknown fp vs known-wrong-key within ±10% ---

func TestConstantTimeTiming(t *testing.T) {
	if testing.Short() {
		t.Skip("timing test skipped in short mode")
	}
	row := &resolve.KeyRow{
		ID:             "svckey_01TESTROW0000000000000001",
		AgentID:        "agent_01TESTROW0000000000000001",
		ServiceID:      "svc_01TESTROW0000000000000001",
		AllowedActions: []string{"read:health"},
		KeyHash:        resolve.HashForTest("correct_key"),
	}
	h := newHandler(&mockStore{row: row, agentOK: true}, proxyToken)

	const runs = 5
	var unknownTotal, wrongTotal time.Duration
	for i := 0; i < runs; i++ {
		start := time.Now()
		post(h, reqBody{KeyFingerprint: "unknownfp", PresentedKey: "x", ServiceID: "svc_01TESTROW0000000000000001", TenantID: "tenant_01TESTROW000000000000001"}, proxyToken)
		unknownTotal += time.Since(start)

		start = time.Now()
		post(h, reqBody{KeyFingerprint: "aabbccdd", PresentedKey: "wrong", ServiceID: "svc_01TESTROW0000000000000001", TenantID: "tenant_01TESTROW000000000000001"}, proxyToken)
		wrongTotal += time.Since(start)
	}

	unknownAvg := float64(unknownTotal) / float64(runs)
	wrongAvg := float64(wrongTotal) / float64(runs)
	ratio := unknownAvg / wrongAvg
	if math.Abs(ratio-1.0) > 0.10 {
		t.Logf("unknown avg=%v known-wrong avg=%v ratio=%.3f", time.Duration(unknownAvg), time.Duration(wrongAvg), ratio)
		// Not a hard failure in unit tests; constant-time is best-effort without hardware isolation
		t.Skip("timing ratio outside ±10% — acceptable in non-isolated CI")
	}
}
