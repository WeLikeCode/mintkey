package egress

import (
	"context"
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

// countingCCExchanger is a test-only ClientCredentialsExchangerIface that counts
// ExchangeClientCredentials calls.
type countingCCExchanger struct {
	calls  int32
	result *credential.ExchangeResult
	err    error
	delay  time.Duration
}

func (c *countingCCExchanger) ExchangeClientCredentials(_ context.Context, _ credential.ClientCredentialsRequest) (*credential.ExchangeResult, error) {
	atomic.AddInt32(&c.calls, 1)
	if c.delay > 0 {
		time.Sleep(c.delay)
	}
	return c.result, c.err
}

func newCountingCCExchanger(token string) *countingCCExchanger {
	return &countingCCExchanger{result: &credential.ExchangeResult{Token: token}}
}

// buildCCPayload builds a minimal client-credentials credential payload.
func buildCCPayload(t *testing.T, tokenURL string) []byte {
	t.Helper()
	return mustMarshal(t, credential.OAuth2ClientCredentialsCredential{
		TokenURL:     tokenURL,
		ClientID:     "cid",
		ClientSecret: "csec",
	})
}

func TestHandleOAuth2ClientCredentials_CacheHit(t *testing.T) {
	tc := cache.NewTokenCache()
	tc.Put("tenant1", "svc1", "cached-cc-token", time.Now().Add(5*time.Minute))

	deps := OAuth2ClientCredentialsDeps{
		Cache:     tc,
		Exchanger: newCountingCCExchanger("should-not-be-used"),
	}
	payload := buildCCPayload(t, "https://cloud.mongodb.com/api/oauth/token")

	result, err := HandleOAuth2ClientCredentials(context.Background(), deps, "tenant1", "svc1", payload)
	require.NoError(t, err)
	assert.Equal(t, "cached-cc-token", result.Token)
	assert.False(t, result.Exchanged)
	assert.Equal(t, "cloud.mongodb.com", result.TokenURLHost)
}

func TestHandleOAuth2ClientCredentials_CacheMiss_ExchangeAndCache(t *testing.T) {
	tc := cache.NewTokenCache()
	ex := newCountingCCExchanger("fresh-cc-token")
	deps := OAuth2ClientCredentialsDeps{Cache: tc, Exchanger: ex}
	payload := buildCCPayload(t, "https://cloud.mongodb.com/api/oauth/token")

	result, err := HandleOAuth2ClientCredentials(context.Background(), deps, "tenant1", "svc1", payload)
	require.NoError(t, err)
	assert.Equal(t, "fresh-cc-token", result.Token)
	assert.True(t, result.Exchanged)
	assert.True(t, result.ExchangeSuccess)
	assert.Equal(t, int32(1), atomic.LoadInt32(&ex.calls))

	// Token cached → second call is a cache hit, no new exchange.
	result2, err := HandleOAuth2ClientCredentials(context.Background(), deps, "tenant1", "svc1", payload)
	require.NoError(t, err)
	assert.Equal(t, "fresh-cc-token", result2.Token)
	assert.False(t, result2.Exchanged)
	assert.Equal(t, int32(1), atomic.LoadInt32(&ex.calls))
}

func TestHandleOAuth2ClientCredentials_ExchangeFails_GracefulDegradation(t *testing.T) {
	tc := cache.NewTokenCache()
	// Near-expiry token: within the 30s buffer (miss on Get) but not fully expired.
	tc.Put("tenant1", "svc1", "degraded-cc-token", time.Now().Add(15*time.Second))

	ex := &countingCCExchanger{err: credential.ErrTokenExchangeFailed}
	deps := OAuth2ClientCredentialsDeps{Cache: tc, Exchanger: ex}
	payload := buildCCPayload(t, "https://cloud.mongodb.com/api/oauth/token")

	result, err := HandleOAuth2ClientCredentials(context.Background(), deps, "tenant1", "svc1", payload)
	require.NoError(t, err)
	assert.Equal(t, "degraded-cc-token", result.Token)
	assert.True(t, result.Exchanged)
	assert.False(t, result.ExchangeSuccess)
}

func TestHandleOAuth2ClientCredentials_ExchangeFails_NoCache_Returns502(t *testing.T) {
	tc := cache.NewTokenCache()
	ex := &countingCCExchanger{err: credential.ErrTokenEndpointUnreachable}
	deps := OAuth2ClientCredentialsDeps{Cache: tc, Exchanger: ex}
	payload := buildCCPayload(t, "https://cloud.mongodb.com/api/oauth/token")

	result, err := HandleOAuth2ClientCredentials(context.Background(), deps, "tenant1", "svc1", payload)
	require.Error(t, err)
	assert.True(t, result.Exchanged)
	assert.False(t, result.ExchangeSuccess)
}

func TestHandleOAuth2ClientCredentials_InvalidPayload(t *testing.T) {
	deps := OAuth2ClientCredentialsDeps{Cache: cache.NewTokenCache(), Exchanger: newCountingCCExchanger("x")}
	_, err := HandleOAuth2ClientCredentials(context.Background(), deps, "tenant1", "svc1", []byte("not-json"))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "parse credential payload")
}

// TestHandleOAuth2ClientCredentials_Singleflight_CoalescesOnMiss verifies that
// N concurrent cache misses coalesce into exactly one exchange.
func TestHandleOAuth2ClientCredentials_Singleflight_CoalescesOnMiss(t *testing.T) {
	const N = 50
	tc := cache.NewTokenCache()
	ex := newCountingCCExchanger("coalesced-cc-token")
	ex.delay = 20 * time.Millisecond

	sf := new(singleflight.Group)
	deps := OAuth2ClientCredentialsDeps{Cache: tc, Exchanger: ex, SF: sf}
	payload := buildCCPayload(t, "https://cloud.mongodb.com/api/oauth/token")

	var wg sync.WaitGroup
	wg.Add(N)
	started := make(chan struct{})
	results := make([]*OAuth2HandlerResult, N)
	errs := make([]error, N)
	for i := 0; i < N; i++ {
		i := i
		go func() {
			defer wg.Done()
			<-started
			results[i], errs[i] = HandleOAuth2ClientCredentials(context.Background(), deps, "t1", "s1", payload)
		}()
	}
	close(started)
	wg.Wait()

	for i, err := range errs {
		require.NoError(t, err, "goroutine %d", i)
		assert.Equal(t, "coalesced-cc-token", results[i].Token, "goroutine %d", i)
	}
	assert.Equal(t, int32(1), atomic.LoadInt32(&ex.calls),
		"expected exactly 1 exchange call, got %d", atomic.LoadInt32(&ex.calls))
}
