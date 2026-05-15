// Package main tests the proxy HTTP handler.
package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/classicalkey"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
	proxyjwt "github.com/mintkey/mintkey/services/proxy-plugin/internal/jwt"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
)

func testHandler() *proxyHandler {
	cfg := &config.Config{
		VaultAddrGRPC:  "localhost:1",
		JWKSEndpoint:   "http://localhost:1/.well-known/jwks.json",
		PluginPort:     8086,
		DefaultTarget:  "http://localhost:1",
		AudEnforcement: config.AudEnforcementPermissive,
	}
	ck := classicalkey.NewHandler(classicalkey.Config{BrokerURL: "http://localhost:1", CacheTTL: 60 * time.Second})
	return newProxyHandler(cfg, vault.NewClient("localhost:1", ""), proxyjwt.NewJWKSRefreshLimiter(), ck, nil)
}

func testHandlerStrict() *proxyHandler {
	cfg := &config.Config{
		VaultAddrGRPC:  "localhost:1",
		JWKSEndpoint:   "http://localhost:1/.well-known/jwks.json",
		PluginPort:     8086,
		DefaultTarget:  "http://localhost:1",
		AudEnforcement: config.AudEnforcementStrict,
	}
	ck := classicalkey.NewHandler(classicalkey.Config{BrokerURL: "http://localhost:1", CacheTTL: 60 * time.Second})
	h := newProxyHandler(cfg, vault.NewClient("localhost:1", ""), proxyjwt.NewJWKSRefreshLimiter(), ck, nil)
	return h
}

// buildTestJWT creates a minimal EdDSA-signed JWT for tests.
// The returned public key must be loaded into handler.pubKeys["testkey"].
func buildTestJWT(t *testing.T, audUUID string) (string, ed25519.PublicKey) {
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
		"aud":   []string{audUUID},
		"tnt":   "tenant-test-uuid-0001",
		"scope": "call",
		"exp":   time.Now().Unix() + 600,
	}
	payload := base64.RawURLEncoding.EncodeToString(mustMarshalJSON(t, claimsMap))

	msg := header + "." + payload
	sig := ed25519.Sign(priv, []byte(msg))
	token := msg + "." + base64.RawURLEncoding.EncodeToString(sig)
	return token, pub
}

func mustMarshalJSON(t *testing.T, v any) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}
	return b
}

// TestProxy_MissingAuthHeader verifies that requests without Authorization → 401.
func TestProxy_MissingAuthHeader(t *testing.T) {
	h := testHandler()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	if rw.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rw.Code)
	}
}

// TestProxy_InvalidJWT verifies that a non-JWT Authorization header → 401.
func TestProxy_InvalidJWT(t *testing.T) {
	h := testHandler()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer not.a.jwt")
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	if rw.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rw.Code)
	}
}

// ---------------------------------------------------------------------------
// ADR-0004 addendum: aud enforcement unit tests
// ---------------------------------------------------------------------------

const (
	testSvcUUIDA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
	testSvcUUIDB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
)

// TestAudEnforcement_Permissive_Match verifies that permissive mode + matching
// aud/URL → proceeds past the aud check (vault call may fail, but not 403).
func TestAudEnforcement_Permissive_Match(t *testing.T) {
	h := testHandler() // permissive
	token, pub := buildTestJWT(t, testSvcUUIDA)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)

	// 403 must NOT happen; vault will be unreachable → 502 or similar.
	if rw.Code == http.StatusForbidden {
		t.Fatalf("permissive+match: unexpected 403")
	}
}

// TestAudEnforcement_Permissive_Mismatch verifies that permissive mode + aud/URL
// mismatch → logs warning but does NOT return 403.
func TestAudEnforcement_Permissive_Mismatch(t *testing.T) {
	h := testHandler() // permissive
	// JWT is for svc A; URL is for svc B.
	token, pub := buildTestJWT(t, testSvcUUIDA)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDB+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)

	if rw.Code == http.StatusForbidden {
		t.Fatalf("permissive+mismatch: must NOT 403 (got 403 body: %s)", rw.Body.String())
	}
}

// TestAudEnforcement_Strict_Match verifies that strict mode + matching aud/URL
// → proceeds past the aud check (vault call may fail, but not 403).
func TestAudEnforcement_Strict_Match(t *testing.T) {
	h := testHandlerStrict()
	token, pub := buildTestJWT(t, testSvcUUIDA)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)

	if rw.Code == http.StatusForbidden {
		t.Fatalf("strict+match: unexpected 403")
	}
}

// TestAudEnforcement_Strict_Mismatch verifies that strict mode + aud/URL
// mismatch → 403 with {"error":"scope mismatch"}.
func TestAudEnforcement_Strict_Mismatch(t *testing.T) {
	h := testHandlerStrict()
	// JWT is for svc A; URL is for svc B.
	token, pub := buildTestJWT(t, testSvcUUIDA)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDB+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)

	if rw.Code != http.StatusForbidden {
		t.Fatalf("strict+mismatch: expected 403, got %d (body: %s)", rw.Code, rw.Body.String())
	}

	body := rw.Body.String()
	if !strings.Contains(body, "scope mismatch") {
		t.Fatalf("strict+mismatch: expected 'scope mismatch' in body, got: %s", body)
	}

	// Must be JSON.
	var respJSON map[string]any
	if err := json.NewDecoder(bytes.NewBufferString(body)).Decode(&respJSON); err != nil {
		t.Fatalf("strict+mismatch: body is not valid JSON: %s", body)
	}
	if respJSON["error"] != "scope mismatch" {
		t.Fatalf("strict+mismatch: expected error=scope mismatch, got: %v", respJSON)
	}
}

// ---------------------------------------------------------------------------
// urlServiceID helper tests
// ---------------------------------------------------------------------------

func TestURLServiceID(t *testing.T) {
	cases := []struct {
		path string
		want string
	}{
		{"/v1/call/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/endpoint", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
		{"/v1/call/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
		{"/v1/call/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
		// No UUID in path → empty
		{"/v1/call/svc_notauuid/endpoint", ""},
		{"/healthz", ""},
		{"/", ""},
		{"", ""},
	}
	for _, tc := range cases {
		got := urlServiceID(tc.path)
		if got != tc.want {
			t.Errorf("urlServiceID(%q) = %q, want %q", tc.path, got, tc.want)
		}
	}
}

func TestIsUUIDShape(t *testing.T) {
	valid := []string{
		"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
		"00000000-0000-0000-0000-000000000000",
		"FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
		"aabbccdd-eeff-0011-2233-445566778899",
	}
	for _, s := range valid {
		if !isUUIDShape(s) {
			t.Errorf("isUUIDShape(%q) = false, want true", s)
		}
	}
	invalid := []string{
		"not-a-uuid",
		"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaZ", // invalid char
		"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa",  // too short
		"svc_AAAAAAAAAABBBBBBBBCCCCCCCCDDDD",   // svc_ prefix
		"",
	}
	for _, s := range invalid {
		if isUUIDShape(s) {
			t.Errorf("isUUIDShape(%q) = true, want false", s)
		}
	}
}
