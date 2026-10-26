package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// buildScopeClaimsJWT signs a test token whose claims are the defaults of the
// other proxy tests merged with extra; a key of extra replaces the default.
// The returned public key must be loaded into handler.pubKeys["testkey"].
func buildScopeClaimsJWT(t *testing.T, aud string, extra map[string]any) (string, ed25519.PublicKey) {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}

	headerMap := map[string]any{"alg": "EdDSA", "typ": "JWT", "kid": "testkey"}
	header := base64.RawURLEncoding.EncodeToString(mustMarshalJSON(t, headerMap))

	claimsMap := map[string]any{
		"iss":   "mintkey/broker",
		"sub":   "agent_test",
		"aud":   []string{aud},
		"tnt":   "tenant-test-uuid-0001",
		"scope": "call",
		"jti":   "jti_scope_test",
		"exp":   time.Now().Unix() + 600,
	}
	for k, v := range extra {
		claimsMap[k] = v
	}
	payload := base64.RawURLEncoding.EncodeToString(mustMarshalJSON(t, claimsMap))

	msg := header + "." + payload
	sig := ed25519.Sign(priv, []byte(msg))
	return msg + "." + base64.RawURLEncoding.EncodeToString(sig), pub
}

func scopeRequest(t *testing.T, h *proxyHandler, token, method, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	return rw
}

func assertScopeRefused(t *testing.T, h *proxyHandler, token, method, path, wantError string) {
	t.Helper()
	rw := scopeRequest(t, h, token, method, path)
	if rw.Code != http.StatusForbidden {
		t.Fatalf("%s %s: status = %d, want %d (body: %s)", method, path, rw.Code, http.StatusForbidden, rw.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rw.Body.Bytes(), &body); err != nil {
		t.Fatalf("%s %s: body is not valid JSON: %s", method, path, rw.Body.String())
	}
	if got := body["error"]; got != wantError {
		t.Fatalf("%s %s: error = %v, want %q (body: %s)", method, path, got, wantError, rw.Body.String())
	}
}

func assertScopeReachesVault(t *testing.T, h *proxyHandler, token, method, path string) {
	t.Helper()
	rw := scopeRequest(t, h, token, method, path)
	if rw.Code != http.StatusBadGateway {
		t.Fatalf("%s %s: status = %d, want %d from the unreachable test vault (body: %s)", method, path, rw.Code, http.StatusBadGateway, rw.Body.String())
	}
}

// TestScopeClaimsRefuseOtherMethodAndPathBeforeVault covers the scenario "other
// methods and paths are refused, the permitted call goes through": a token
// limited to GET under /v1/messages refuses other methods and paths with 403
// before the credential fetch, while permitted requests reach the test vault.
func TestScopeClaimsRefuseOtherMethodAndPathBeforeVault_C_60d4b695(t *testing.T) {
	h := testHandler()
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, map[string]any{
		"methods":     []any{"GET"},
		"path_prefix": "/v1/messages",
	})
	h.pubKeys["testkey"] = pub

	assertScopeRefused(t, h, token, http.MethodPost, "/v1/messages/x", "method not permitted")
	assertScopeRefused(t, h, token, http.MethodHead, "/v1/messages/x", "method not permitted")
	assertScopeRefused(t, h, token, http.MethodGet, "/v1/other", "path not permitted")
	assertScopeRefused(t, h, token, http.MethodGet, "/v1/messagesX", "path not permitted")

	assertScopeReachesVault(t, h, token, http.MethodGet, "/v1/messages/x")
	assertScopeReachesVault(t, h, token, http.MethodGet, "/v1/messages")
	assertScopeReachesVault(t, h, token, http.MethodGet, "/"+testSvcUUIDA+"/v1/messages/x")
}

// TestScopeClaimsRefuseDotSegmentsAndMalformedClaims covers the scenario "dot
// segments and malformed claims are refused": a dot or dot-dot segment and a
// path_prefix or methods claim of the wrong shape are refused with 403.
func TestScopeClaimsRefuseDotSegmentsAndMalformedClaims_C_97127a0e(t *testing.T) {
	h := testHandler()

	dotToken, dotPub := buildScopeClaimsJWT(t, testSvcUUIDA, map[string]any{"path_prefix": "/v1/messages"})
	h.pubKeys["testkey"] = dotPub
	assertScopeRefused(t, h, dotToken, http.MethodGet, "/v1/messages/../admin", "path not permitted")
	assertScopeRefused(t, h, dotToken, http.MethodGet, "/v1/messages/./x", "path not permitted")

	for _, methods := range []any{"GET", []any{}} {
		token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, map[string]any{"methods": methods})
		h.pubKeys["testkey"] = pub
		assertScopeRefused(t, h, token, http.MethodGet, "/v1/messages/x", "method not permitted")
	}

	for _, prefix := range []any{5, "v1"} {
		token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, map[string]any{"path_prefix": prefix})
		h.pubKeys["testkey"] = pub
		assertScopeRefused(t, h, token, http.MethodGet, "/v1/messages/x", "path not permitted")
	}
}
