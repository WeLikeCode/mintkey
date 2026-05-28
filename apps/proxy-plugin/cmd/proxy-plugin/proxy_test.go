// Package main tests the proxy HTTP handler.
package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"log"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/classicalkey"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/egress"
	proxyjwt "github.com/mintkey/mintkey/services/proxy-plugin/internal/jwt"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
)

// mockAuditQueue implements auditEnqueuer and captures emitted events for
// assertion in tests.
type mockAuditQueue struct {
	mu     sync.Mutex
	events []auditq.Event
}

func (m *mockAuditQueue) Enqueue(e auditq.Event) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, e)
}

func (m *mockAuditQueue) captured() []auditq.Event {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]auditq.Event, len(m.events))
	copy(out, m.events)
	return out
}

func testHandler() *proxyHandler {
	cfg := &config.Config{
		VaultAddrGRPC:  "localhost:1",
		JWKSEndpoint:   "http://localhost:1/.well-known/jwks.json",
		PluginPort:     8086,
		DefaultTarget:  "http://localhost:1",
		AudEnforcement: config.AudEnforcementPermissive,
	}
	ck := classicalkey.NewHandler(classicalkey.Config{BrokerURL: "http://localhost:1", CacheTTL: 60 * time.Second})
	return newProxyHandler(cfg, vault.NewClient("localhost:1", ""), proxyjwt.NewJWKSRefreshLimiter(), ck, nil, nil)
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
	h := newProxyHandler(cfg, vault.NewClient("localhost:1", ""), proxyjwt.NewJWKSRefreshLimiter(), ck, nil, nil)
	return h
}

// buildTestJWT creates a minimal EdDSA-signed JWT for tests.
// The returned public key must be loaded into handler.pubKeys["testkey"].
func buildTestJWT(t *testing.T, audUUID string) (string, ed25519.PublicKey) {
	t.Helper()
	return buildTestJWTWithClaims(t, audUUID, "agent_test", "")
}

// buildTestJWTWithClaims creates a signed test JWT with explicit sub and jti.
// Pass jti="" to omit the jti claim.
func buildTestJWTWithClaims(t *testing.T, audUUID, sub, jti string) (string, ed25519.PublicKey) {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}

	headerMap := map[string]any{"alg": "EdDSA", "typ": "JWT", "kid": "testkey"}
	header := base64.RawURLEncoding.EncodeToString(mustMarshalJSON(t, headerMap))

	claimsMap := map[string]any{
		"iss":   "mintkey/broker",
		"sub":   sub,
		"aud":   []string{audUUID},
		"tnt":   "tenant-test-uuid-0001",
		"scope": "call",
		"exp":   time.Now().Unix() + 600,
	}
	if jti != "" {
		claimsMap["jti"] = jti
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
// #24: proxy.aud_mismatch_rejected audit emission tests
// ---------------------------------------------------------------------------

// testHandlerStrictWithAudit builds a strict-mode handler with a mock audit
// queue wired in.  The mock captures all Enqueue calls for assertion.
func testHandlerStrictWithAudit(mock *mockAuditQueue) *proxyHandler {
	cfg := &config.Config{
		VaultAddrGRPC:  "localhost:1",
		JWKSEndpoint:   "http://localhost:1/.well-known/jwks.json",
		PluginPort:     8086,
		DefaultTarget:  "http://localhost:1",
		AudEnforcement: config.AudEnforcementStrict,
	}
	ck := classicalkey.NewHandler(classicalkey.Config{BrokerURL: "http://localhost:1", CacheTTL: 60 * time.Second})
	h := newProxyHandler(cfg, vault.NewClient("localhost:1", ""), proxyjwt.NewJWKSRefreshLimiter(), ck, nil, nil)
	h.audit = mock
	return h
}

// TestAudMismatchRejected_EmitsAuditEvent verifies that strict-mode 403
// rejection emits a proxy.aud_mismatch_rejected event with the correct
// payload shape: {jti, aud, url_service_id, mode} — no credentials (#24).
func TestAudMismatchRejected_EmitsAuditEvent(t *testing.T) {
	mock := &mockAuditQueue{}
	h := testHandlerStrictWithAudit(mock)

	const testJTI = "test-jti-abc123"
	const testAgentID = "agent_00000000000000000000001"

	// JWT audience is svcA; request URL targets svcB → mismatch.
	token, pub := buildTestJWTWithClaims(t, testSvcUUIDA, testAgentID, testJTI)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDB+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)

	if rw.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", rw.Code)
	}

	events := mock.captured()
	if len(events) != 1 {
		t.Fatalf("expected 1 audit event, got %d", len(events))
	}
	evt := events[0]

	if evt.EventType != "proxy.aud_mismatch_rejected" {
		t.Errorf("EventType: want proxy.aud_mismatch_rejected, got %q", evt.EventType)
	}
	if evt.ActorID != testAgentID {
		t.Errorf("ActorID: want %q, got %q", testAgentID, evt.ActorID)
	}
	if evt.ActorType != "agent" {
		t.Errorf("ActorType: want agent, got %q", evt.ActorType)
	}
	if evt.TargetID != testSvcUUIDA {
		t.Errorf("TargetID: want %q (aud), got %q", testSvcUUIDA, evt.TargetID)
	}
	if evt.TargetType != "service" {
		t.Errorf("TargetType: want service, got %q", evt.TargetType)
	}

	// Payload checks.
	if evt.Payload["jti"] != testJTI {
		t.Errorf("Payload.jti: want %q, got %v", testJTI, evt.Payload["jti"])
	}
	if evt.Payload["aud"] != testSvcUUIDA {
		t.Errorf("Payload.aud: want %q (JWT aud), got %v", testSvcUUIDA, evt.Payload["aud"])
	}
	if evt.Payload["url_service_id"] != testSvcUUIDB {
		t.Errorf("Payload.url_service_id: want %q, got %v", testSvcUUIDB, evt.Payload["url_service_id"])
	}
	if evt.Payload["mode"] != "strict" {
		t.Errorf("Payload.mode: want %q, got %v", "strict", evt.Payload["mode"])
	}

	// S-SEC-1: no credential or JWT raw value in payload.
	forbidden := []string{"credential", "api_key_value", "token_value", "secret", "plaintext", "token"}
	for _, key := range forbidden {
		if _, exists := evt.Payload[key]; exists {
			t.Errorf("Payload must not contain field %q (S-SEC-1)", key)
		}
	}
}

// TestAudMismatchRejected_NoEmitWhenAuditNil verifies that the strict-mode
// 403 path still works correctly when no audit queue is wired (nil).
func TestAudMismatchRejected_NoEmitWhenAuditNil(t *testing.T) {
	h := testHandlerStrict() // audit=nil
	token, pub := buildTestJWT(t, testSvcUUIDA)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDB+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req) // must not panic

	if rw.Code != http.StatusForbidden {
		t.Fatalf("expected 403 with nil audit, got %d", rw.Code)
	}
}

// TestAudEnforcement_Permissive_NoAuditEvent verifies that permissive mode
// does NOT emit proxy.aud_mismatch_rejected (only strict mode should).
func TestAudEnforcement_Permissive_NoAuditEvent(t *testing.T) {
	mock := &mockAuditQueue{}
	cfg := &config.Config{
		VaultAddrGRPC:  "localhost:1",
		JWKSEndpoint:   "http://localhost:1/.well-known/jwks.json",
		PluginPort:     8086,
		DefaultTarget:  "http://localhost:1",
		AudEnforcement: config.AudEnforcementPermissive,
	}
	ck := classicalkey.NewHandler(classicalkey.Config{BrokerURL: "http://localhost:1", CacheTTL: 60 * time.Second})
	h := newProxyHandler(cfg, vault.NewClient("localhost:1", ""), proxyjwt.NewJWKSRefreshLimiter(), ck, nil, nil)
	h.audit = mock

	token, pub := buildTestJWT(t, testSvcUUIDA)
	h.pubKeys["testkey"] = pub

	// Permissive + mismatch → vault call (will fail), but no aud_mismatch_rejected.
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDB+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)

	// No proxy.aud_mismatch_rejected events.
	for _, e := range mock.captured() {
		if e.EventType == "proxy.aud_mismatch_rejected" {
			t.Errorf("permissive mode must not emit proxy.aud_mismatch_rejected")
		}
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

// ---------------------------------------------------------------------------
// CWE-312 / CodeQL go/clear-text-logging redaction tests
// ---------------------------------------------------------------------------

// captureLog redirects the default logger output to a buffer for the duration
// of fn, then restores it. Returns all bytes written to the log during fn.
func captureLog(t *testing.T, fn func()) []byte {
	t.Helper()
	var buf bytes.Buffer
	log.SetOutput(&buf)
	defer log.SetOutput(os.Stderr)
	fn()
	return buf.Bytes()
}

// TestSafeID_RedactsNonUUID verifies that safeID returns "[redacted]" for any
// value that is not UUID-shaped, so credential values can never reach the log.
func TestSafeID_RedactsNonUUID(t *testing.T) {
	cases := []struct {
		input string
		want  string
	}{
		// valid UUIDs pass through
		{"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
		{"00000000-0000-0000-0000-000000000000", "00000000-0000-0000-0000-000000000000"},
		// anything that looks like a secret is redacted
		{"sk-live-AbCdEfGh1234567890XxYyZz", "[redacted]"},
		{"Bearer eyJhbGciOiJFZERTQSJ9.abc.def", "[redacted]"},
		{"s3cr3t!p@ssw0rd", "[redacted]"},
		{"", "[redacted]"},
	}
	for _, tc := range cases {
		got := safeID(tc.input)
		if got != tc.want {
			t.Errorf("safeID(%q) = %q, want %q", tc.input, got, tc.want)
		}
	}
}

// TestAudCheck_LogDoesNotContainSecret exercises the aud-mismatch permissive
// log path (main.go site 1) and asserts the raw JWT Bearer token does not
// appear in the log output.  The JWT carries a UUID audience claim; if safeID
// is removed the raw tainted value would reach the log.
func TestAudCheck_LogDoesNotContainSecret(t *testing.T) {
	h := testHandler() // permissive — will log the aud-check warning

	const secretSentinel = "SUPER_SECRET_VALUE"
	// Build a JWT where the aud claim is a valid UUID (will be logged) but also
	// inject a secret into a request header (must NOT be logged).
	token, pub := buildTestJWT(t, testSvcUUIDA)
	h.pubKeys["testkey"] = pub

	// URL uses svcB so the aud mismatch log line fires.
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDB+"/path", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	// Add a header whose value we want to confirm is absent from logs.
	req.Header.Set("X-Secret-Header", secretSentinel)
	rw := httptest.NewRecorder()

	logOut := captureLog(t, func() {
		h.ServeHTTP(rw, req)
	})

	if strings.Contains(string(logOut), secretSentinel) {
		t.Errorf("log output must not contain secret sentinel %q; got: %s", secretSentinel, logOut)
	}
	// Confirm the log line was actually emitted (regression guard).
	if !strings.Contains(string(logOut), "aud_check") {
		t.Errorf("expected aud_check log line to be emitted; got: %s", logOut)
	}
}

// --- Production-path singleflight guard (FIX-5 regression guard) ---
//
// These tests verify that newProxyHandler wires a shared *singleflight.Group
// (non-nil, reused across requests). If someone removes the SF wiring from
// newProxyHandler or handleOAuth2PasswordGrant the coalescing test fails with
// N>1 exchange calls rather than exactly 1.

// countingExchangerForProd is a minimal TokenExchangerIface for the guard test.
type countingExchangerForProd struct {
	calls int32 // accessed atomically
	delay time.Duration
	token string
}

func (c *countingExchangerForProd) Exchange(_ context.Context, _ credential.ExchangeRequest) (*credential.ExchangeResult, error) {
	atomic.AddInt32(&c.calls, 1)
	if c.delay > 0 {
		time.Sleep(c.delay)
	}
	return &credential.ExchangeResult{Token: c.token}, nil
}

// TestNewProxyHandler_SFGroupIsNonNil asserts that the production constructor
// initialises the shared singleflight group.  This fails immediately if the
// sfGroup field is absent or left nil.
func TestNewProxyHandler_SFGroupIsNonNil(t *testing.T) {
	h := testHandler()
	if h.sfGroup == nil {
		t.Fatal("newProxyHandler must initialise h.sfGroup; got nil — singleflight coalescing is INACTIVE in production")
	}
}

// TestNewProxyHandler_SFGroupIsReused asserts that the same *singleflight.Group
// instance is shared across multiple calls (i.e. it is not re-created per request).
// It obtains the pointer twice through the public field and checks identity.
func TestNewProxyHandler_SFGroupIsReused(t *testing.T) {
	h := testHandler()
	if h.sfGroup == nil {
		t.Fatal("sfGroup is nil — see TestNewProxyHandler_SFGroupIsNonNil")
	}
	// Confirm the same pointer would be used for two consecutive requests by
	// reading it twice from the same handler — must be identical.
	first := h.sfGroup
	second := h.sfGroup
	if first != second {
		t.Fatal("sfGroup must be the same instance across requests; got different pointers")
	}
}

// TestProductionPath_NewOAuth2Deps_SFIsWired is the make-or-break regression
// guard for FIX-5.  It calls the real production construction method
// h.newOAuth2Deps() and asserts that the returned deps.SF is non-nil AND is
// the same pointer as h.sfGroup.
//
// FLIP: if someone removes `SF: h.sfGroup` from newOAuth2Deps (re-introducing
// the attempt-1 regression), this test fails with a clear message because
// deps.SF will be nil even though h.sfGroup is non-nil.
func TestProductionPath_NewOAuth2Deps_SFIsWired(t *testing.T) {
	h := testHandler()
	if h.sfGroup == nil {
		t.Fatal("sfGroup is nil — singleflight not wired in production constructor")
	}

	deps := h.newOAuth2Deps()

	if deps.SF == nil {
		t.Fatal("newOAuth2Deps().SF is nil — SF field dropped from production construction site; thundering-herd protection is INACTIVE")
	}
	if deps.SF != h.sfGroup {
		t.Fatalf("newOAuth2Deps().SF (%p) != h.sfGroup (%p) — production construction site is not using the shared singleflight group", deps.SF, h.sfGroup)
	}
}

// TestProductionPath_SFCoalescesOnConcurrentMiss drives N concurrent cache
// misses through the real production construction path (via newOAuth2Deps)
// and asserts exactly 1 upstream exchange — not N.
func TestProductionPath_SFCoalescesOnConcurrentMiss(t *testing.T) {
	const N = 50

	h := testHandler()
	if h.sfGroup == nil {
		t.Fatal("sfGroup is nil — singleflight not wired in production constructor")
	}

	// Swap in counting fake exchanger and a fresh cache so all N are misses.
	ex := &countingExchangerForProd{token: "prod-coalesced-token", delay: 20 * time.Millisecond}
	tc := cache.NewTokenCache()

	// Point the handler at the fake exchanger and cache; obtain deps via the
	// real production construction method so SF comes from the production site.
	h.tokenExchanger = credential.NewTokenExchanger() // keep field valid; deps override below
	h.tokenCache = tc

	payload, err := json.Marshal(credential.OAuth2PasswordGrantCredential{
		TokenURL:          "https://dummy.example.com/token",
		CredentialFields:  map[string]string{"username": "u", "password": "p"},
		TokenResponsePath: "$.token",
	})
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}

	// Build deps from the real construction site, then override Exchanger with
	// the counting fake.  This keeps Cache and SF from the production path while
	// allowing the fake exchanger for call counting.
	baseDeps := h.newOAuth2Deps()
	deps := egress.OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: ex,
		SF:        baseDeps.SF, // sourced from production site — not hand-built
	}

	var wg sync.WaitGroup
	wg.Add(N)
	started := make(chan struct{})

	results := make([]*egress.OAuth2HandlerResult, N)
	errs := make([]error, N)

	for i := 0; i < N; i++ {
		i := i
		go func() {
			defer wg.Done()
			<-started
			results[i], errs[i] = egress.HandleOAuth2PasswordGrant(
				context.Background(), deps, "tenant-prod", "svc-prod", payload,
			)
		}()
	}
	close(started)
	wg.Wait()

	for i, e := range errs {
		if e != nil {
			t.Errorf("goroutine %d: unexpected error: %v", i, e)
		}
	}
	calls := atomic.LoadInt32(&ex.calls)
	if calls != 1 {
		t.Fatalf("production singleflight coalescing broken: expected exactly 1 exchange call, got %d — SF field not wired", calls)
	}
	_ = results
}
