// Tests for the proxy plugin classical-key branch.
//
// TDD: written before implementation per task 5.7/5.8 discipline.
// Sources: design §2; Req 2.1, 2.2, 2.3, 2.4, 2.6, 4.2, 4.4, 6.4, 10.3, 10.5, 10.6; ADR-0018.
package classicalkey_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/classicalkey"
)

// --- Helpers ---

// fakeAuditCapture captures proxy.hit calls.
type fakeAuditCapture struct {
	mu   sync.Mutex
	hits []classicalkey.ProxyHitPayload
}

func (f *fakeAuditCapture) EmitProxyHit(_ context.Context, p classicalkey.ProxyHitPayload) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.hits = append(f.hits, p)
}

func (f *fakeAuditCapture) lastHit() *classicalkey.ProxyHitPayload {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.hits) == 0 {
		return nil
	}
	h := f.hits[len(f.hits)-1]
	return &h
}

// fakeBroker wraps an httptest.Server that serves a broker-like response.
type fakeBroker struct {
	srv      *httptest.Server
	response any
	status   int
	calls    int
	mu       sync.Mutex
}

func newFakeBroker(status int, response any) *fakeBroker {
	fb := &fakeBroker{status: status, response: response}
	fb.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fb.mu.Lock()
		fb.calls++
		fb.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(fb.status)
		_ = json.NewEncoder(w).Encode(fb.response)
	}))
	return fb
}

func (fb *fakeBroker) callCount() int {
	fb.mu.Lock()
	defer fb.mu.Unlock()
	return fb.calls
}

func (fb *fakeBroker) close() { fb.srv.Close() }

func goodResolution(serviceID string) map[string]any {
	return map[string]any{
		"api_key_id":      "svckey_01PROXYTEST00000000000001",
		"agent_id":        "agent_01PROXYTEST000000000000001",
		"service_id":      serviceID,
		"allowed_actions": []string{"read:health"},
		"expires_at":      nil,
	}
}

// --- Tests ---

// TestPrefixDispatch verifies that mk_svckey_ is detected as classical key.
func TestPrefixDispatch(t *testing.T) {
	if !classicalkey.IsClassicalKey("mk_svckey_AAAABBBBCCCCDDDD") {
		t.Fatal("mk_svckey_ should be detected as classical key")
	}
	if classicalkey.IsClassicalKey("eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9") {
		t.Fatal("eyJ JWT should not be detected as classical key")
	}
	if classicalkey.IsClassicalKey("Bearer eyJhbGci") {
		t.Fatal("Bearer JWT should not be detected as classical key")
	}
}

// TestCacheHitSkipsBroker verifies that a cached resolution doesn't call the broker.
func TestCacheHitSkipsBroker(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	broker := newFakeBroker(http.StatusOK, goodResolution(svcID))
	defer broker.close()

	audit := &fakeAuditCapture{}
	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:       broker.srv.URL,
		ProxyToken:      "test_proxy_token",
		CacheTTL:        30 * time.Second,
		AuditEmitter:    audit,
	})

	cred := "mk_svckey_AAAABBBBCCCCDDDD"
	ctx := context.Background()

	// First call → cache miss → broker call.
	res, err := h.Resolve(ctx, cred, svcID, "tenant_01PROXYTEST0000000000000")
	if err != nil {
		t.Fatalf("first resolve: %v", err)
	}
	if res == nil {
		t.Fatal("expected resolution, got nil")
	}
	if broker.callCount() != 1 {
		t.Fatalf("expected 1 broker call, got %d", broker.callCount())
	}

	// Second call → cache hit → no broker call.
	res2, err := h.Resolve(ctx, cred, svcID, "tenant_01PROXYTEST0000000000000")
	if err != nil {
		t.Fatalf("second resolve: %v", err)
	}
	if res2 == nil {
		t.Fatal("expected resolution from cache")
	}
	if broker.callCount() != 1 {
		t.Fatalf("expected still 1 broker call, got %d", broker.callCount())
	}
}

// TestCacheMissCallsBroker verifies broker is called on cache miss.
func TestCacheMissCallsBroker(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	broker := newFakeBroker(http.StatusOK, goodResolution(svcID))
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	_, _ = h.Resolve(context.Background(), "mk_svckey_KEY1", svcID, "tenant_01")
	_, _ = h.Resolve(context.Background(), "mk_svckey_KEY2", svcID, "tenant_01") // different key = different fingerprint
	if broker.callCount() != 2 {
		t.Fatalf("expected 2 broker calls for 2 different keys, got %d", broker.callCount())
	}
}

// TestBrokerReturns401IsRelayed verifies 401 from broker returns error with code.
func TestBrokerReturns401IsRelayed(t *testing.T) {
	broker := newFakeBroker(http.StatusUnauthorized, map[string]any{
		"mintkey:code": "api_key_invalid",
		"title":        "API key invalid",
	})
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	_, err := h.Resolve(context.Background(), "mk_svckey_BAD", "svc_01", "tenant_01")
	if err == nil {
		t.Fatal("expected error for 401 from broker")
	}
	ke, ok := err.(*classicalkey.KeyError)
	if !ok {
		t.Fatalf("expected KeyError, got %T: %v", err, err)
	}
	if ke.Code != "api_key_invalid" {
		t.Fatalf("expected api_key_invalid, got %q", ke.Code)
	}
}

// TestResolverDownNoCacheReturns503 verifies fail-closed when broker is unreachable.
func TestResolverDownNoCacheReturns503(t *testing.T) {
	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    "http://127.0.0.1:19999", // port nothing listens on
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	_, err := h.Resolve(context.Background(), "mk_svckey_UNREACHABLE", "svc_01", "tenant_01")
	if err == nil {
		t.Fatal("expected error when broker unreachable")
	}
	ke, ok := err.(*classicalkey.KeyError)
	if !ok {
		t.Fatalf("expected KeyError, got %T: %v", err, err)
	}
	if ke.Code != "api_key_resolution_unavailable" {
		t.Fatalf("expected api_key_resolution_unavailable, got %q", ke.Code)
	}
	if ke.HTTPStatus != http.StatusServiceUnavailable {
		t.Fatalf("expected 503, got %d", ke.HTTPStatus)
	}
}

// TestPerRequestCheckWrongService verifies service ID mismatch is caught.
func TestPerRequestCheckWrongService(t *testing.T) {
	const boundSvc = "svc_BOUND000000000000000000001"
	broker := newFakeBroker(http.StatusOK, goodResolution(boundSvc))
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	res, _ := h.Resolve(context.Background(), "mk_svckey_SVC", boundSvc, "tenant_01")
	if res == nil {
		t.Fatal("expected resolution")
	}

	req := &classicalkey.RequestContext{
		ServiceID:    "svc_DIFFERENT0000000000000001",
		Method:       "GET",
		Path:         "/health",
		ClientIP:     "10.0.0.1",
	}
	err := h.CheckRequest(res, req)
	if err == nil {
		t.Fatal("expected error for wrong service")
	}
	if err.(*classicalkey.KeyError).Code != "api_key_wrong_service" {
		t.Fatalf("expected api_key_wrong_service, got %q", err.(*classicalkey.KeyError).Code)
	}
}

// TestPerRequestCheckExpired verifies expiry is caught per-request.
func TestPerRequestCheckExpired(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	past := time.Now().Add(-time.Hour)
	resp := map[string]any{
		"api_key_id":      "svckey_01PROXYTEST00000000000001",
		"agent_id":        "agent_01PROXYTEST000000000000001",
		"service_id":      svcID,
		"allowed_actions": []string{"read:health"},
		"expires_at":      past.Format(time.RFC3339),
	}
	broker := newFakeBroker(http.StatusOK, resp)
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	res, _ := h.Resolve(context.Background(), "mk_svckey_EXP", svcID, "tenant_01")
	err := h.CheckRequest(res, &classicalkey.RequestContext{ServiceID: svcID, Method: "GET", Path: "/health", ClientIP: "10.0.0.1"})
	if err == nil {
		t.Fatal("expected error for expired key")
	}
	if err.(*classicalkey.KeyError).Code != "api_key_expired" {
		t.Fatalf("expected api_key_expired, got %q", err.(*classicalkey.KeyError).Code)
	}
}

// TestPerRequestCheckActionNotAllowed verifies action check.
func TestPerRequestCheckActionNotAllowed(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	resp := map[string]any{
		"api_key_id":      "svckey_01PROXYTEST00000000000001",
		"agent_id":        "agent_01PROXYTEST000000000000001",
		"service_id":      svcID,
		"allowed_actions": []string{"read:health"}, // only read:health allowed
		"expires_at":      nil,
	}
	broker := newFakeBroker(http.StatusOK, resp)
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	res, _ := h.Resolve(context.Background(), "mk_svckey_ACTION", svcID, "tenant_01")
	// Use POST which would map to "write:*" or some non-allowed action; use the
	// service action map (MVP: "POST" → "write:*"). Since "write:*" is not in
	// ["read:health"], this should fail.
	err := h.CheckRequest(res, &classicalkey.RequestContext{
		ServiceID:      svcID,
		Method:         "POST",
		Path:           "/data",
		ClientIP:       "10.0.0.1",
		RequestedAction: "write:data", // explicit action for test
	})
	if err == nil {
		t.Fatal("expected error for action not allowed")
	}
	if err.(*classicalkey.KeyError).Code != "api_key_action_not_allowed" {
		t.Fatalf("expected api_key_action_not_allowed, got %q", err.(*classicalkey.KeyError).Code)
	}
}

// TestPerRequestCheckConstraintIPAllowlist verifies source_ip_allowlist constraint.
func TestPerRequestCheckConstraintIPAllowlist(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	resp := map[string]any{
		"api_key_id":      "svckey_01PROXYTEST00000000000001",
		"agent_id":        "agent_01PROXYTEST000000000000001",
		"service_id":      svcID,
		"allowed_actions": []string{"read:health"},
		"constraints": map[string]any{
			"source_ip_allowlist": []any{"10.0.0.0/8"},
		},
		"expires_at": nil,
	}
	broker := newFakeBroker(http.StatusOK, resp)
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	res, _ := h.Resolve(context.Background(), "mk_svckey_IP", svcID, "tenant_01")

	// Allowed IP passes.
	err := h.CheckRequest(res, &classicalkey.RequestContext{ServiceID: svcID, Method: "GET", Path: "/health", ClientIP: "10.1.2.3"})
	if err != nil {
		t.Fatalf("expected pass for allowed IP: %v", err)
	}

	// Disallowed IP fails.
	err = h.CheckRequest(res, &classicalkey.RequestContext{ServiceID: svcID, Method: "GET", Path: "/health", ClientIP: "192.168.1.1"})
	if err == nil {
		t.Fatal("expected error for disallowed IP")
	}
	if err.(*classicalkey.KeyError).Code != "api_key_constraint_failed" {
		t.Fatalf("expected api_key_constraint_failed, got %q", err.(*classicalkey.KeyError).Code)
	}
}

// TestAuthMethodSpanAttribute verifies mintkey.auth_method is set on the span.
func TestAuthMethodSpanAttribute(t *testing.T) {
	attrs := classicalkey.SpanAttributesForClassicalKey()
	found := false
	for _, a := range attrs {
		if a.Key == "mintkey.auth_method" && a.Value.AsString() == "api_key" {
			found = true
		}
	}
	if !found {
		t.Fatal("expected mintkey.auth_method=api_key in span attributes")
	}
	// key_fingerprint must NOT be in span attributes.
	for _, a := range attrs {
		if a.Key == "mintkey.key_fingerprint" {
			t.Fatal("key_fingerprint must not be a span attribute (Req 11.4)")
		}
	}
}

// TestProxyHitCarriesAuthMethod verifies proxy.hit includes auth_method and api_key_id.
func TestProxyHitCarriesAuthMethod(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	broker := newFakeBroker(http.StatusOK, goodResolution(svcID))
	defer broker.close()

	audit := &fakeAuditCapture{}
	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: audit,
	})

	res, _ := h.Resolve(context.Background(), "mk_svckey_HITME", svcID, "tenant_01")
	_ = h.EmitHit(context.Background(), res, "mk_svckey_HITME", svcID, 200, "GET", "/health", 50)

	hit := audit.lastHit()
	if hit == nil {
		t.Fatal("no proxy.hit emitted")
	}
	if hit.AuthMethod != "api_key" {
		t.Fatalf("expected auth_method=api_key, got %q", hit.AuthMethod)
	}
	if hit.APIKeyID != "svckey_01PROXYTEST00000000000001" {
		t.Fatalf("unexpected api_key_id: %q", hit.APIKeyID)
	}
	if hit.KeyFingerprint == "" {
		t.Fatal("key_fingerprint should be set in proxy.hit")
	}
}

// TestProxyHitUsedAtCoalesced verifies that used_at is only set once per 60s per api_key_id.
func TestProxyHitUsedAtCoalesced(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	broker := newFakeBroker(http.StatusOK, goodResolution(svcID))
	defer broker.close()

	audit := &fakeAuditCapture{}
	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: audit,
	})

	res, _ := h.Resolve(context.Background(), "mk_svckey_COALESCE", svcID, "tenant_01")

	// First hit: used_at should be set.
	_ = h.EmitHit(context.Background(), res, "mk_svckey_COALESCE", svcID, 200, "GET", "/health", 10)
	hit1 := audit.lastHit()
	if hit1 == nil || hit1.UsedAt == nil {
		t.Fatal("first hit should have used_at")
	}

	// Second hit within 60s: used_at should be nil (coalesced).
	_ = h.EmitHit(context.Background(), res, "mk_svckey_COALESCE", svcID, 200, "GET", "/health", 10)
	hit2 := audit.lastHit()
	if hit2 != nil && hit2.UsedAt != nil {
		t.Fatal("second hit within 60s should not have used_at (coalesced)")
	}
}

// TestCacheEvictionOnApiKeyRevoked verifies eviction on api_key.revoked.
func TestCacheEvictionOnApiKeyRevoked(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	broker := newFakeBroker(http.StatusOK, goodResolution(svcID))
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	cred := "mk_svckey_EVICT"
	_, _ = h.Resolve(context.Background(), cred, svcID, "tenant_01")
	if broker.callCount() != 1 {
		t.Fatal("expected 1 broker call after first resolve")
	}

	// Evict by fingerprint.
	fp := classicalkey.Fingerprint(cred)
	h.EvictByFingerprint(fp)

	// Next resolve should call broker again (cache was evicted).
	_, _ = h.Resolve(context.Background(), cred, svcID, "tenant_01")
	if broker.callCount() != 2 {
		t.Fatalf("expected 2 broker calls after eviction, got %d", broker.callCount())
	}
}

// TestCacheEvictionOnAgentRevoked verifies eviction of all keys for an agent.
func TestCacheEvictionOnAgentRevoked(t *testing.T) {
	const svcID = "svc_01PROXYTEST000000000000001"
	broker := newFakeBroker(http.StatusOK, goodResolution(svcID))
	defer broker.close()

	h := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    broker.srv.URL,
		ProxyToken:   "test_proxy_token",
		CacheTTL:     30 * time.Second,
		AuditEmitter: &fakeAuditCapture{},
	})

	// Resolve two keys that both resolve to the same agent_id.
	for _, cred := range []string{"mk_svckey_AGENTEVICT1", "mk_svckey_AGENTEVICT2"} {
		_, _ = h.Resolve(context.Background(), cred, svcID, "tenant_01")
	}
	if broker.callCount() != 2 {
		t.Fatalf("expected 2 broker calls, got %d", broker.callCount())
	}

	// Evict by agent_id (the fake broker always returns the same agent_id).
	h.EvictByAgentID("agent_01PROXYTEST000000000000001")

	// Both keys should be evicted — next resolves call broker again.
	for _, cred := range []string{"mk_svckey_AGENTEVICT1", "mk_svckey_AGENTEVICT2"} {
		_, _ = h.Resolve(context.Background(), cred, svcID, "tenant_01")
	}
	if broker.callCount() != 4 {
		t.Fatalf("expected 4 total broker calls after agent eviction, got %d", broker.callCount())
	}
}
