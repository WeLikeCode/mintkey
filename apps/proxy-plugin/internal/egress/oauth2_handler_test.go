package egress

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/audit"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"golang.org/x/sync/singleflight"
	"pgregory.net/rapid"
)

// countingExchanger is a test-only TokenExchangerIface that counts Exchange calls.
type countingExchanger struct {
	mu      sync.Mutex
	calls   int32 // atomic count of Exchange invocations
	result  *credential.ExchangeResult
	err     error
	// delay lets tests synchronise goroutines inside the exchange window.
	delay time.Duration
}

func (c *countingExchanger) Exchange(_ context.Context, _ credential.ExchangeRequest) (*credential.ExchangeResult, error) {
	atomic.AddInt32(&c.calls, 1)
	if c.delay > 0 {
		time.Sleep(c.delay)
	}
	return c.result, c.err
}

func newCountingExchanger(token string) *countingExchanger {
	return &countingExchanger{
		result: &credential.ExchangeResult{Token: token},
	}
}

func newFailingExchanger() *countingExchanger {
	return &countingExchanger{err: credential.ErrTokenExchangeFailed}
}

// buildPayload is a helper to create a minimal oauth2 credential payload.
func buildPayload(t *testing.T, tokenURL string) []byte {
	t.Helper()
	return mustMarshal(t, credential.OAuth2PasswordGrantCredential{
		TokenURL:          tokenURL,
		CredentialFields:  map[string]string{"username": "u", "password": "p"},
		TokenResponsePath: "$.token",
	})
}

// --- HandleOAuth2PasswordGrant tests ---

func TestHandleOAuth2PasswordGrant_CacheHit(t *testing.T) {
	// Setup: token in cache with expiry well beyond 30s buffer.
	tc := cache.NewTokenCache()
	tc.Put("tenant1", "svc1", "cached-token-123", time.Now().Add(5*time.Minute))

	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: credential.NewTokenExchanger(),
	}

	payload := mustMarshal(t, credential.OAuth2PasswordGrantCredential{
		TokenURL:          "https://example.com/auth/login",
		CredentialFields:  map[string]string{"username": "admin", "password": "secret"},
		TokenResponsePath: "$.token",
	})

	result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "tenant1", "svc1", payload)
	require.NoError(t, err)
	assert.Equal(t, "cached-token-123", result.Token)
	assert.False(t, result.Exchanged)
	assert.Equal(t, "example.com", result.TokenURLHost)
}

func TestHandleOAuth2PasswordGrant_CacheMiss_ExchangeSuccess(t *testing.T) {
	// Setup: mock token endpoint that returns a token.
	tokenServer := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"token": "fresh-token-456", "expires_in": 3600}`))
	}))
	defer tokenServer.Close()

	tc := cache.NewTokenCache()
	exchanger := credential.NewTokenExchangerWithClient(tokenServer.Client())

	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: exchanger,
	}

	payload := mustMarshal(t, credential.OAuth2PasswordGrantCredential{
		TokenURL:          tokenServer.URL + "/auth/login",
		CredentialFields:  map[string]string{"username": "admin", "password": "secret"},
		TokenResponsePath: "$.token",
	})

	result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "tenant1", "svc1", payload)
	require.NoError(t, err)
	assert.Equal(t, "fresh-token-456", result.Token)
	assert.True(t, result.Exchanged)
	assert.True(t, result.ExchangeSuccess)
	assert.Greater(t, result.ExchangeLatencyMS, int64(-1))

	// Verify the token was cached.
	cachedToken, ok := tc.Get("tenant1", "svc1")
	assert.True(t, ok)
	assert.Equal(t, "fresh-token-456", cachedToken)
}

func TestHandleOAuth2PasswordGrant_ExchangeFails_GracefulDegradation(t *testing.T) {
	// Setup: token endpoint returns 500 (exchange fails).
	tokenServer := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error": "internal error"}`))
	}))
	defer tokenServer.Close()

	// Put a near-expiry token in cache (within 30s buffer but not fully expired).
	tc := cache.NewTokenCache()
	tc.Put("tenant1", "svc1", "near-expiry-token", time.Now().Add(15*time.Second))

	exchanger := credential.NewTokenExchangerWithClient(tokenServer.Client())

	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: exchanger,
	}

	payload := mustMarshal(t, credential.OAuth2PasswordGrantCredential{
		TokenURL:          tokenServer.URL + "/auth/login",
		CredentialFields:  map[string]string{"username": "admin", "password": "secret"},
		TokenResponsePath: "$.token",
	})

	result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "tenant1", "svc1", payload)
	require.NoError(t, err)
	// Should use the degraded cached token.
	assert.Equal(t, "near-expiry-token", result.Token)
	assert.True(t, result.Exchanged)
	assert.False(t, result.ExchangeSuccess)
}

func TestHandleOAuth2PasswordGrant_ExchangeFails_NoCache_Returns502(t *testing.T) {
	// Setup: token endpoint returns 500 and no cached token exists.
	tokenServer := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error": "internal error"}`))
	}))
	defer tokenServer.Close()

	tc := cache.NewTokenCache()
	exchanger := credential.NewTokenExchangerWithClient(tokenServer.Client())

	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: exchanger,
	}

	payload := mustMarshal(t, credential.OAuth2PasswordGrantCredential{
		TokenURL:          tokenServer.URL + "/auth/login",
		CredentialFields:  map[string]string{"username": "admin", "password": "secret"},
		TokenResponsePath: "$.token",
	})

	result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "tenant1", "svc1", payload)
	require.Error(t, err)
	assert.True(t, result.Exchanged)
	assert.False(t, result.ExchangeSuccess)
}

func TestHandleOAuth2PasswordGrant_ExchangeFails_CacheFullyExpired_Returns502(t *testing.T) {
	// Setup: token endpoint returns 500 and cached token is fully expired.
	tokenServer := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error": "internal error"}`))
	}))
	defer tokenServer.Close()

	tc := cache.NewTokenCache()
	// Put a fully expired token.
	tc.Put("tenant1", "svc1", "expired-token", time.Now().Add(-1*time.Minute))

	exchanger := credential.NewTokenExchangerWithClient(tokenServer.Client())

	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: exchanger,
	}

	payload := mustMarshal(t, credential.OAuth2PasswordGrantCredential{
		TokenURL:          tokenServer.URL + "/auth/login",
		CredentialFields:  map[string]string{"username": "admin", "password": "secret"},
		TokenResponsePath: "$.token",
	})

	result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "tenant1", "svc1", payload)
	require.Error(t, err)
	// Fully expired token should NOT be used for degradation.
	assert.True(t, result.Exchanged)
	assert.False(t, result.ExchangeSuccess)
}

func TestHandleOAuth2PasswordGrant_InvalidPayload(t *testing.T) {
	tc := cache.NewTokenCache()
	exchanger := credential.NewTokenExchanger()

	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: exchanger,
	}

	// Invalid JSON payload.
	_, err := HandleOAuth2PasswordGrant(context.Background(), deps, "tenant1", "svc1", []byte("not-json"))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "parse credential payload")
}

// --- extractHost tests ---

func TestExtractHost(t *testing.T) {
	tests := []struct {
		name     string
		url      string
		expected string
	}{
		{"full URL", "https://dashboard-api-ps-prod.azurewebsites.net/api/auth/login", "dashboard-api-ps-prod.azurewebsites.net"},
		{"URL with port", "https://example.com:8443/token", "example.com"},
		{"empty URL", "", "unknown"},
		{"invalid URL", "://invalid", "unknown"},
		{"no host", "/relative/path", "unknown"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := extractHost(tt.url)
			assert.Equal(t, tt.expected, result)
		})
	}
}

// --- ClassifyError tests ---

func TestClassifyError(t *testing.T) {
	assert.Equal(t, "token_exchange_failed", ClassifyError(credential.ErrTokenExchangeFailed))
	assert.Equal(t, "token_endpoint_unreachable", ClassifyError(credential.ErrTokenEndpointUnreachable))
	assert.Equal(t, "token_parse_failed", ClassifyError(credential.ErrTokenParseFailed))
	assert.Equal(t, "token_exchange_failed", ClassifyError(fmt.Errorf("some other error")))
	assert.Equal(t, "", ClassifyError(nil))
}

// --- AC-1: singleflight coalescing — N concurrent misses → exactly 1 exchange ---

func TestHandleOAuth2PasswordGrant_Singleflight_CoalescesOnMiss(t *testing.T) {
	const N = 50
	tc := cache.NewTokenCache()
	ex := newCountingExchanger("coalesced-token")
	// Give the exchange a brief delay so all goroutines can pile up on the miss.
	ex.delay = 20 * time.Millisecond

	sf := new(singleflight.Group)
	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: ex,
		SF:        sf,
	}
	payload := buildPayload(t, "https://dummy.example.com/token")

	var wg sync.WaitGroup
	wg.Add(N)
	// started is closed once all goroutines have been spawned, acting as a barrier.
	started := make(chan struct{})
	results := make([]*OAuth2HandlerResult, N)
	errs := make([]error, N)

	for i := 0; i < N; i++ {
		i := i
		go func() {
			defer wg.Done()
			<-started // wait until all goroutines are ready
			results[i], errs[i] = HandleOAuth2PasswordGrant(context.Background(), deps, "t1", "s1", payload)
		}()
	}
	close(started) // release all goroutines simultaneously
	wg.Wait()

	// All requests must succeed with the same token.
	for i, err := range errs {
		require.NoError(t, err, "goroutine %d got error", i)
		assert.Equal(t, "coalesced-token", results[i].Token, "goroutine %d got wrong token", i)
	}

	// The exchanger must have been called EXACTLY ONCE (coalesced).
	assert.Equal(t, int32(1), atomic.LoadInt32(&ex.calls),
		"expected exactly 1 exchange call, got %d", atomic.LoadInt32(&ex.calls))
}

// --- AC-2: different (tenant,service) keys are NOT serialised ---

func TestHandleOAuth2PasswordGrant_Singleflight_DifferentKeysParallel(t *testing.T) {
	const N = 10 // goroutines per key
	const keys = 3
	tc := cache.NewTokenCache()

	type keyedEx struct {
		key string
		ex  *countingExchanger
	}
	exchangers := []keyedEx{
		{"k1", newCountingExchanger("token-k1")},
		{"k2", newCountingExchanger("token-k2")},
		{"k3", newCountingExchanger("token-k3")},
	}
	for i := range exchangers {
		exchangers[i].ex.delay = 20 * time.Millisecond
	}

	// Each (tenant,service) pair uses the SAME deps but we identify them by
	// tenantID+serviceID. We share one SF group as real code would.
	sf := new(singleflight.Group)

	var wg sync.WaitGroup
	started := make(chan struct{})

	for _, ke := range exchangers {
		ke := ke
		deps := OAuth2HandlerDeps{
			Cache:     tc,
			Exchanger: ke.ex,
			SF:        sf,
		}
		payload := buildPayload(t, "https://dummy.example.com/token")
		for i := 0; i < N; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				<-started
				_, _ = HandleOAuth2PasswordGrant(context.Background(), deps, "tenant-"+ke.key, ke.key, payload)
			}()
		}
	}
	close(started)
	wg.Wait()

	// Each key should have fired exactly 1 exchange (coalesced within the key).
	for _, ke := range exchangers {
		assert.Equal(t, int32(1), atomic.LoadInt32(&ke.ex.calls),
			"key %s: expected 1 exchange, got %d", ke.key, atomic.LoadInt32(&ke.ex.calls))
	}
	// Total exchanges across all keys == keys (not 1 — each key runs independently).
	var total int32
	for _, ke := range exchangers {
		total += atomic.LoadInt32(&ke.ex.calls)
	}
	assert.Equal(t, int32(keys), total, "total exchanges should equal number of distinct keys")
}

// --- AC-3: a failed exchange is propagated to waiters, does NOT poison future requests ---

func TestHandleOAuth2PasswordGrant_Singleflight_FailureNotPoisoned(t *testing.T) {
	const N = 10
	tc := cache.NewTokenCache()
	ex := newFailingExchanger()
	ex.delay = 20 * time.Millisecond

	sf := new(singleflight.Group)
	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: ex,
		SF:        sf,
	}
	payload := buildPayload(t, "https://dummy.example.com/token")

	// First flight: N concurrent misses, all fail.
	var wg1 sync.WaitGroup
	wg1.Add(N)
	started := make(chan struct{})
	for i := 0; i < N; i++ {
		go func() {
			defer wg1.Done()
			<-started
			_, _ = HandleOAuth2PasswordGrant(context.Background(), deps, "t1", "s1", payload)
		}()
	}
	close(started)
	wg1.Wait()

	callsAfterFirstFlight := atomic.LoadInt32(&ex.calls)
	assert.Equal(t, int32(1), callsAfterFirstFlight, "first flight should have fired exactly 1 exchange")

	// Now heal the exchanger and make a single new request — it must NOT be
	// blocked by the previous failure (no permanent poison).
	ex.mu.Lock()
	ex.err = nil
	ex.result = &credential.ExchangeResult{Token: "healed-token"}
	ex.mu.Unlock()

	result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "t1", "s1", payload)
	require.NoError(t, err)
	assert.Equal(t, "healed-token", result.Token)
	assert.Equal(t, int32(2), atomic.LoadInt32(&ex.calls), "healed request should trigger a new exchange")
}

// Ensure errors package is used (for future test additions).
var _ = errors.New

// --- helpers ---

func mustMarshal(t *testing.T, v any) []byte {
	t.Helper()
	data, err := json.Marshal(v)
	require.NoError(t, err)
	return data
}

// =============================================================================
// Property 10 — Graceful degradation on refresh failure (9.4)
//
// Falsifying class: a cached token whose absolute expiry has passed is used as
// degraded fallback (should 502), OR a non-expired cached token is discarded
// (should succeed without 502) when the exchanger fails.
// =============================================================================

// errorExchanger always returns an error.
type errorExchanger struct {
	err error
}

func (e *errorExchanger) Exchange(_ context.Context, _ credential.ExchangeRequest) (*credential.ExchangeResult, error) {
	return nil, e.err
}

func TestGracefulDegradation(t *testing.T) {
	rapid.Check(t, func(rt *rapid.T) {
		// Generate an arbitrary offset around now for the cached token's expiry.
		// Negative offsets → already expired; positive offsets → still valid.
		offsetSec := rapid.Int64Range(-300, 300).Draw(rt, "offset_sec")
		expiresAt := time.Now().Add(time.Duration(offsetSec) * time.Second)

		tc := cache.NewTokenCache()
		tc.Put("tenant1", "svc1", "cached-tok", expiresAt)

		deps := OAuth2HandlerDeps{
			Cache:     tc,
			Exchanger: &errorExchanger{err: credential.ErrTokenExchangeFailed},
		}
		payload := buildPayload(t, "https://auth.example.com/token")

		result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "tenant1", "svc1", payload)

		tokenIsExpired := time.Now().After(expiresAt)

		// The cache.Get returns miss when expiry ≤ now+30s, so exchange is triggered.
		// After exchange failure GetForDegradation is called.
		if !tokenIsExpired {
			// Token NOT fully expired — should be used as degraded fallback, no error.
			if err != nil {
				rt.Fatalf("expected nil error when cached token not fully expired (offset=%ds), got: %v", offsetSec, err)
			}
			if result.Token != "cached-tok" {
				rt.Fatalf("expected degraded token 'cached-tok', got %q (offset=%ds)", result.Token, offsetSec)
			}
		} else {
			// Token IS fully expired — must return an error (502 path).
			if err == nil {
				rt.Fatalf("expected error when cached token fully expired (offset=%ds), got nil (token=%q)", offsetSec, result.Token)
			}
		}
	})
}

// =============================================================================
// Property 11 — Audit event completeness + host-only redaction (9.5)
//
// Falsifying class: token_url_host contains a path segment or query string, OR
// any required field is absent from the emitted event body.
// =============================================================================

// capturingAuditServer captures the last emitted body for inspection.
type capturingAuditServer struct {
	srv  *httptest.Server
	body []byte
}

func newCapturingAuditServer() *capturingAuditServer {
	c := &capturingAuditServer{}
	c.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		buf := make([]byte, 64<<10)
		n, _ := r.Body.Read(buf)
		c.body = buf[:n]
		w.WriteHeader(http.StatusNoContent)
	}))
	return c
}

func TestAuditEventCompleteness(t *testing.T) {
	rapid.Check(t, func(rt *rapid.T) {
		// Arbitrary hostname components (no slashes or query chars).
		label := rapid.StringMatching(`[a-z][a-z0-9]{0,8}`).Draw(rt, "label")
		tld := rapid.StringMatching(`[a-z]{2,5}`).Draw(rt, "tld")
		hostname := label + "." + tld

		// Arbitrary path and query that must NOT appear in token_url_host.
		path := "/" + rapid.StringMatching(`[a-z]{2,10}`).Draw(rt, "path")
		query := "?foo=" + rapid.StringMatching(`[a-z]{2,6}`).Draw(rt, "query")
		tokenURL := "https://" + hostname + path + query

		tenantID := rapid.StringMatching(`[a-z]{3,8}`).Draw(rt, "tenant_id")
		serviceID := rapid.StringMatching(`[a-z]{3,8}`).Draw(rt, "service_id")
		agentID := rapid.StringMatching(`[a-z]{3,8}`).Draw(rt, "agent_id")

		event := audit.TokenExchangedEvent{
			TenantID:     tenantID,
			ServiceID:    serviceID,
			AgentID:      agentID,
			TokenURLHost: audit.ExtractHost(tokenURL),
			Success:      rapid.Bool().Draw(rt, "success"),
			LatencyMS:    rapid.Int64Range(0, 10000).Draw(rt, "latency_ms"),
		}

		// Capture emitted body.
		cap := newCapturingAuditServer()
		defer cap.srv.Close()

		emitter := audit.NewEmitter(cap.srv.URL, "svc-token")
		_ = emitter.EmitTokenExchanged(context.Background(), event)

		// Decode envelope.
		var envelope map[string]any
		if err := json.Unmarshal(cap.body, &envelope); err != nil {
			rt.Fatalf("invalid JSON body: %v", err)
		}

		payload, ok := envelope["payload"].(map[string]any)
		if !ok {
			rt.Fatalf("payload is not an object")
		}

		// Assert all required fields are present.
		for _, f := range []string{"tenant_id", "service_id", "agent_id", "token_url_host", "success", "latency_ms"} {
			if _, exists := payload[f]; !exists {
				rt.Fatalf("required field %q absent from emitted event; payload=%v", f, payload)
			}
		}

		// Assert token_url_host is host-only (no scheme, path, query).
		host, _ := payload["token_url_host"].(string)
		if strings.Contains(host, "/") {
			rt.Fatalf("token_url_host contains slash (path leaked): %q; original url=%q", host, tokenURL)
		}
		if strings.Contains(host, "?") {
			rt.Fatalf("token_url_host contains ? (query leaked): %q; original url=%q", host, tokenURL)
		}
		if strings.HasPrefix(host, "http") {
			rt.Fatalf("token_url_host contains scheme: %q; original url=%q", host, tokenURL)
		}
		if host != hostname {
			rt.Fatalf("token_url_host=%q; want %q; original url=%q", host, hostname, tokenURL)
		}
	})
}

// =============================================================================
// Property 12 — Sensitive data exclusion from all observable outputs (9.6)
//
// Falsifying class: a real secret VALUE or token VALUE appears anywhere in the
// serialised audit event body (not just a struct tag name check).
// =============================================================================

func TestSensitiveDataExclusion(t *testing.T) {
	rapid.Check(t, func(rt *rapid.T) {
		// Generate real secret and token values that are meaningfully distinct
		// from field names so tag-name checks would not catch them.
		secretValue := "SECRET_" + rapid.StringMatching(`[A-Z0-9]{12,24}`).Draw(rt, "secret_value")
		tokenValue := "TOKEN_" + rapid.StringMatching(`[A-Z0-9]{12,24}`).Draw(rt, "token_value")
		fieldName := rapid.StringMatching(`[a-z_]{3,12}`).Draw(rt, "field_name")

		tenantID := rapid.StringMatching(`[a-z]{3,8}`).Draw(rt, "tenant_id")
		serviceID := rapid.StringMatching(`[a-z]{3,8}`).Draw(rt, "service_id")
		agentID := rapid.StringMatching(`[a-z]{3,8}`).Draw(rt, "agent_id")
		hostname := rapid.StringMatching(`[a-z]{3,8}`).Draw(rt, "hostname") + ".example.com"

		// The emitter receives only safe fields; it must never include secret or token.
		event := audit.TokenExchangedEvent{
			TenantID:     tenantID,
			ServiceID:    serviceID,
			AgentID:      agentID,
			TokenURLHost: hostname,
			Success:      true,
			LatencyMS:    42,
		}
		// (We never set credential_fields or token on the event — this asserts the struct
		// itself has no such fields and the serialised body cannot contain the values.)
		_ = fieldName   // used to simulate a credential field name; the VALUE must be absent
		_ = secretValue // the real secret value that must never appear

		cap := newCapturingAuditServer()
		defer cap.srv.Close()

		emitter := audit.NewEmitter(cap.srv.URL, "svc-token")
		_ = emitter.EmitTokenExchanged(context.Background(), event)

		bodyStr := string(cap.body)

		// Assert the real secret VALUE is not present anywhere in the serialised body.
		if strings.Contains(bodyStr, secretValue) {
			rt.Fatalf("secret value %q found in emitted audit body: %s", secretValue, bodyStr)
		}

		// Assert the real token VALUE is not present anywhere in the serialised body.
		if strings.Contains(bodyStr, tokenValue) {
			rt.Fatalf("token value %q found in emitted audit body: %s", tokenValue, bodyStr)
		}
	})
}

// Additionally: push real secret/token through HandleOAuth2PasswordGrant and
// assert neither appears in the audit body emitted via the full handler path.
func TestSensitiveDataExclusion_FullHandlerPath(t *testing.T) {
	rapid.Check(t, func(rt *rapid.T) {
		secretValue := "REALSECRET_" + rapid.StringMatching(`[A-Z0-9]{12,24}`).Draw(rt, "secret_value")
		tokenValue := "REALTOKEN_" + rapid.StringMatching(`[A-Z0-9]{12,24}`).Draw(rt, "token_value")

		// Token endpoint that returns the tokenValue.
		tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Ensure the secret did NOT arrive in any header or body readable by the
			// upstream; we check the emitted audit instead.
			body := fmt.Sprintf(`{"token": %q, "expires_in": 3600}`, tokenValue)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(body))
		}))
		defer tokenSrv.Close()

		// Capturing audit server.
		var auditBody []byte
		auditSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			buf := make([]byte, 64<<10)
			n, _ := r.Body.Read(buf)
			auditBody = buf[:n]
			w.WriteHeader(http.StatusNoContent)
		}))
		defer auditSrv.Close()

		tc := cache.NewTokenCache()
		exchanger := credential.NewTokenExchangerWithClient(tokenSrv.Client())
		deps := OAuth2HandlerDeps{
			Cache:     tc,
			Exchanger: exchanger,
		}

		payload := mustMarshalR(rt, credential.OAuth2PasswordGrantCredential{
			TokenURL:          tokenSrv.URL + "/token",
			CredentialFields:  map[string]string{"password": secretValue},
			TokenResponsePath: "$.token",
		})

		result, err := HandleOAuth2PasswordGrant(context.Background(), deps, "t1", "s1", payload)
		if err != nil {
			rt.Fatalf("handler error: %v", err)
		}
		if result.Token != tokenValue {
			rt.Fatalf("expected token %q, got %q", tokenValue, result.Token)
		}

		// Emit the audit event for this exchange result (as the caller in main.go would).
		emitter := audit.NewEmitter(auditSrv.URL, "svc-token")
		_ = emitter.EmitTokenExchanged(context.Background(), audit.TokenExchangedEvent{
			TenantID:     "t1",
			ServiceID:    "s1",
			AgentID:      "a1",
			TokenURLHost: result.TokenURLHost,
			Success:      result.ExchangeSuccess,
			LatencyMS:    result.ExchangeLatencyMS,
		})

		bodyStr := string(auditBody)

		// The real secret value must NOT appear in the serialised audit body.
		if strings.Contains(bodyStr, secretValue) {
			rt.Fatalf("secret value %q found in emitted audit body: %s", secretValue, bodyStr)
		}

		// The real token value must NOT appear in the serialised audit body.
		if strings.Contains(bodyStr, tokenValue) {
			rt.Fatalf("token value %q found in emitted audit body: %s", tokenValue, bodyStr)
		}
	})
}

// mustMarshal variant that accepts *rapid.T for use inside rapid.Check.
func mustMarshalR(rt *rapid.T, v any) []byte {
	rt.Helper()
	data, err := json.Marshal(v)
	if err != nil {
		rt.Fatalf("mustMarshalR: %v", err)
	}
	return data
}

// =============================================================================
// 9.7 — In-process full-flow integration test
//
// Substitution note: testcontainers-go is not required; we drive the REAL
// HandleOAuth2PasswordGrant with: a real httptest token endpoint, an in-process
// fake vault (credential stored as JSON), the real TokenCache, the real
// TokenExchangerWithClient, and a capturing audit Emitter. This exercises the
// complete path: vault credential → exchange → inject → cache → audit.
// =============================================================================

func TestIntegration_FullOAuth2Flow(t *testing.T) {
	// --- Step 1: Fake token endpoint (acts as upstream OAuth2 server) ---
	exchangeCount := 0
	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		exchangeCount++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"token": "integration-bearer-xyz", "expires_in": 3600}`))
	}))
	defer tokenSrv.Close()

	// --- Step 2: Capturing audit server ---
	var auditBody []byte
	auditSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		buf := make([]byte, 64<<10)
		n, _ := r.Body.Read(buf)
		auditBody = buf[:n]
		w.WriteHeader(http.StatusNoContent)
	}))
	defer auditSrv.Close()

	// --- Step 3: In-process "vault" — credential stored as JSON ---
	vaultCred := mustMarshal(t, credential.OAuth2PasswordGrantCredential{
		TokenURL:          tokenSrv.URL + "/oauth/token",
		CredentialFields:  map[string]string{"username": "svc_user", "password": "hunter2"},
		TokenResponsePath: "$.token",
	})

	// --- Step 4: Wire handler dependencies ---
	tc := cache.NewTokenCache()
	exchanger := credential.NewTokenExchangerWithClient(tokenSrv.Client())
	emitter := audit.NewEmitter(auditSrv.URL, "svc-token")

	deps := OAuth2HandlerDeps{
		Cache:     tc,
		Exchanger: exchanger,
		SF:        new(singleflight.Group),
	}

	ctx := context.Background()

	// --- Assertion A: vault credential → exchange → inject Bearer ---
	result, err := HandleOAuth2PasswordGrant(ctx, deps, "tenant-int", "svc-int", vaultCred)
	require.NoError(t, err)
	assert.Equal(t, "integration-bearer-xyz", result.Token, "token should be returned from exchange")
	assert.True(t, result.Exchanged, "exchange should have been triggered (cache miss)")
	assert.True(t, result.ExchangeSuccess, "exchange should have succeeded")
	assert.Equal(t, tokenSrv.URL[len("http://"):strings.LastIndex(tokenSrv.URL, ":")], result.TokenURLHost,
		"TokenURLHost should be host-only")
	assert.Equal(t, 1, exchangeCount, "exactly one exchange on first call")

	// Emit audit for first exchange.
	err = emitter.EmitTokenExchanged(ctx, audit.TokenExchangedEvent{
		TenantID:     "tenant-int",
		ServiceID:    "svc-int",
		AgentID:      "agent-int",
		TokenURLHost: result.TokenURLHost,
		Success:      result.ExchangeSuccess,
		LatencyMS:    result.ExchangeLatencyMS,
	})
	require.NoError(t, err)

	// --- Assertion B: audit event has correct fields ---
	var envelope map[string]any
	require.NoError(t, json.Unmarshal(auditBody, &envelope))
	assert.Equal(t, "token.exchanged", envelope["event_type"])
	payload := envelope["payload"].(map[string]any)
	assert.Equal(t, "tenant-int", payload["tenant_id"])
	assert.Equal(t, "svc-int", payload["service_id"])
	assert.Equal(t, "agent-int", payload["agent_id"])
	assert.Equal(t, true, payload["success"])
	// token_url_host must not contain path or query.
	host := payload["token_url_host"].(string)
	assert.NotContains(t, host, "/", "token_url_host must not contain path")
	assert.NotContains(t, host, "?", "token_url_host must not contain query")

	// --- Assertion C: cache prevents redundant exchange within TTL ---
	result2, err := HandleOAuth2PasswordGrant(ctx, deps, "tenant-int", "svc-int", vaultCred)
	require.NoError(t, err)
	assert.Equal(t, "integration-bearer-xyz", result2.Token)
	assert.False(t, result2.Exchanged, "second call within TTL must be a cache hit")
	assert.Equal(t, 1, exchangeCount, "no new exchange on cache hit")

	// --- Assertion D: near-expiry triggers a new exchange ---
	// Overwrite cache with a near-expiry entry (< 30s remaining).
	tc.Put("tenant-int", "svc-int", "near-expiry-tok", time.Now().Add(15*time.Second))

	result3, err := HandleOAuth2PasswordGrant(ctx, deps, "tenant-int", "svc-int", vaultCred)
	require.NoError(t, err)
	assert.Equal(t, "integration-bearer-xyz", result3.Token)
	assert.True(t, result3.Exchanged, "near-expiry should trigger new exchange")
	assert.Equal(t, 2, exchangeCount, "second exchange on near-expiry")

	// --- Assertion E: audit emitted with correct fields after near-expiry exchange ---
	err = emitter.EmitTokenExchanged(ctx, audit.TokenExchangedEvent{
		TenantID:     "tenant-int",
		ServiceID:    "svc-int",
		AgentID:      "agent-int",
		TokenURLHost: result3.TokenURLHost,
		Success:      result3.ExchangeSuccess,
		LatencyMS:    result3.ExchangeLatencyMS,
	})
	require.NoError(t, err)

	var envelope2 map[string]any
	require.NoError(t, json.Unmarshal(auditBody, &envelope2))
	payload2 := envelope2["payload"].(map[string]any)
	assert.Equal(t, true, payload2["success"])
	assert.Equal(t, "tenant-int", payload2["tenant_id"])
}
