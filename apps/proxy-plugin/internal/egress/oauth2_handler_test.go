package egress

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

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

// --- helpers ---

func mustMarshal(t *testing.T, v any) []byte {
	t.Helper()
	data, err := json.Marshal(v)
	require.NoError(t, err)
	return data
}
