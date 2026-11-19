package issue_test

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// postScopeIssue posts a valid /v1/issue request with the scope-claim fields in
// extra merged into the base body.
func postScopeIssue(t *testing.T, h http.Handler, extra map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	body := map[string]any{
		"agent_id":    "agent_01HZ0000000000000000000001",
		"service_id":  "svc_01HZ0000000000000000000002",
		"tenant_id":   "tenant_01HZ0000000000000000000003",
		"scope":       "call",
		"ttl_seconds": 300,
	}
	for k, v := range extra {
		body[k] = v
	}
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal request body: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/issue", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", testMCPToken)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	return w
}

// scopeTokenClaims base64url-decodes the middle segment of a JWT and returns
// its claims.
func scopeTokenClaims(t *testing.T, token string) map[string]any {
	t.Helper()
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Fatalf("token = %q: want 3 dot-separated parts, got %d", token, len(parts))
	}
	claimsJSON, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		t.Fatalf("decode claims segment: %v", err)
	}
	var claims map[string]any
	if err := json.Unmarshal(claimsJSON, &claims); err != nil {
		t.Fatalf("unmarshal claims: %v", err)
	}
	return claims
}

// TestIssueSignsMethodsAndPathPrefixClaims_C_95b500fb covers the scenario "the
// limits are signed as claims": methods are signed uppercased in request order,
// path_prefix unchanged, and neither key is present when the fields are absent.
func TestIssueSignsMethodsAndPathPrefixClaims_C_95b500fb(t *testing.T) {
	h := newTestHandler(t)

	withLimits := postScopeIssue(t, h, map[string]any{
		"methods":     []string{"get", "POST"},
		"path_prefix": "/v1/messages",
	})
	if withLimits.Code != http.StatusOK {
		t.Fatalf("request with limits: status = %d, want 200; body: %s", withLimits.Code, withLimits.Body.String())
	}
	var withResp map[string]any
	if err := json.Unmarshal(withLimits.Body.Bytes(), &withResp); err != nil {
		t.Fatalf("unmarshal response with limits: %v", err)
	}
	withToken, ok := withResp["token"].(string)
	if !ok || withToken == "" {
		t.Fatalf("token missing or empty in response: %v", withResp)
	}
	claims := scopeTokenClaims(t, withToken)
	methods, ok := claims["methods"].([]any)
	if !ok {
		t.Fatalf("methods claim = %v (%T), want a list", claims["methods"], claims["methods"])
	}
	if len(methods) != 2 || methods[0] != "GET" || methods[1] != "POST" {
		t.Fatalf("methods claim = %v, want [GET POST]", methods)
	}
	if got := claims["path_prefix"]; got != "/v1/messages" {
		t.Fatalf("path_prefix claim = %v, want /v1/messages", got)
	}

	withoutLimits := postScopeIssue(t, h, nil)
	if withoutLimits.Code != http.StatusOK {
		t.Fatalf("request without limits: status = %d, want 200; body: %s", withoutLimits.Code, withoutLimits.Body.String())
	}
	var withoutResp map[string]any
	if err := json.Unmarshal(withoutLimits.Body.Bytes(), &withoutResp); err != nil {
		t.Fatalf("unmarshal response without limits: %v", err)
	}
	withoutToken, ok := withoutResp["token"].(string)
	if !ok || withoutToken == "" {
		t.Fatalf("token missing or empty in response: %v", withoutResp)
	}
	bare := scopeTokenClaims(t, withoutToken)
	if _, ok := bare["methods"]; ok {
		t.Fatalf("token without limits carries methods claim: %v", bare["methods"])
	}
	if _, ok := bare["path_prefix"]; ok {
		t.Fatalf("token without limits carries path_prefix claim: %v", bare["path_prefix"])
	}
}

// TestIssueRefusesInvalidScopeClaims_C_f5923c53 covers the scenario "each
// invalid limit is refused": every invalid methods/path_prefix body answers 400
// validation_failed and issues no token.
func TestIssueRefusesInvalidScopeClaims_C_f5923c53(t *testing.T) {
	h := newTestHandler(t)

	cases := []struct {
		name string
		body map[string]any
	}{
		{"empty methods", map[string]any{"methods": []string{}}},
		{"unknown method FETCH", map[string]any{"methods": []string{"FETCH"}}},
		{"duplicate method ignoring case", map[string]any{"methods": []string{"GET", "get"}}},
		{"relative path_prefix", map[string]any{"path_prefix": "v1/messages"}},
		{"dot segment in path_prefix", map[string]any{"path_prefix": "/v1/../admin"}},
		{"query in path_prefix", map[string]any{"path_prefix": "/v1/messages?x=1"}},
		{"empty segment in path_prefix", map[string]any{"path_prefix": "/v1//x"}},
		{"percent-encoding in path_prefix", map[string]any{"path_prefix": "/v1/%2e%2e"}},
		{"methods with service_kind", map[string]any{"methods": []string{"GET"}, "service_kind": "email"}},
	}

	for _, tc := range cases {
		w := postScopeIssue(t, h, tc.body)
		if w.Code != http.StatusBadRequest {
			t.Fatalf("%s: status = %d, want 400; body: %s", tc.name, w.Code, w.Body.String())
		}
		var body map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
			t.Fatalf("%s: unmarshal error body: %v", tc.name, err)
		}
		if body["mintkey:code"] != "validation_failed" {
			t.Fatalf("%s: mintkey:code = %v, want validation_failed", tc.name, body["mintkey:code"])
		}
		if _, ok := body["token"]; ok {
			t.Fatalf("%s: response holds a token field: %v", tc.name, body)
		}
	}
}
