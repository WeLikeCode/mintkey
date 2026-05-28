package egress

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"golang.org/x/sync/singleflight"
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
