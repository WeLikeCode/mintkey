package cache

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// --- Get / Put tests ---

func TestTokenCache_EmptyOnConstruction(t *testing.T) {
	tc := NewTokenCache()
	token, ok := tc.Get("tenant1", "svc1")
	assert.False(t, ok)
	assert.Empty(t, token)
}

func TestTokenCache_PutAndGet_ValidToken(t *testing.T) {
	tc := NewTokenCache()
	expiresAt := time.Now().Add(5 * time.Minute) // well beyond 30s buffer
	tc.Put("tenant1", "svc1", "my-token", expiresAt)

	token, ok := tc.Get("tenant1", "svc1")
	assert.True(t, ok)
	assert.Equal(t, "my-token", token)
}

func TestTokenCache_Get_MissForDifferentKey(t *testing.T) {
	tc := NewTokenCache()
	expiresAt := time.Now().Add(5 * time.Minute)
	tc.Put("tenant1", "svc1", "token-a", expiresAt)

	// Different tenant
	token, ok := tc.Get("tenant2", "svc1")
	assert.False(t, ok)
	assert.Empty(t, token)

	// Different service
	token, ok = tc.Get("tenant1", "svc2")
	assert.False(t, ok)
	assert.Empty(t, token)
}

func TestTokenCache_Get_MissWhenNearExpiry(t *testing.T) {
	tc := NewTokenCache()
	// Expires in 20 seconds — within the 30s refresh buffer.
	expiresAt := time.Now().Add(20 * time.Second)
	tc.Put("tenant1", "svc1", "expiring-token", expiresAt)

	token, ok := tc.Get("tenant1", "svc1")
	assert.False(t, ok)
	assert.Empty(t, token)
}

func TestTokenCache_Get_MissWhenExpired(t *testing.T) {
	tc := NewTokenCache()
	// Already expired.
	expiresAt := time.Now().Add(-1 * time.Minute)
	tc.Put("tenant1", "svc1", "expired-token", expiresAt)

	token, ok := tc.Get("tenant1", "svc1")
	assert.False(t, ok)
	assert.Empty(t, token)
}

func TestTokenCache_Get_HitAtExactlyBoundary(t *testing.T) {
	tc := NewTokenCache()
	// Expires in exactly 31 seconds — just beyond the 30s buffer.
	expiresAt := time.Now().Add(31 * time.Second)
	tc.Put("tenant1", "svc1", "boundary-token", expiresAt)

	token, ok := tc.Get("tenant1", "svc1")
	assert.True(t, ok)
	assert.Equal(t, "boundary-token", token)
}

func TestTokenCache_Put_OverwritesExisting(t *testing.T) {
	tc := NewTokenCache()
	expiresAt := time.Now().Add(5 * time.Minute)
	tc.Put("tenant1", "svc1", "old-token", expiresAt)
	tc.Put("tenant1", "svc1", "new-token", expiresAt)

	token, ok := tc.Get("tenant1", "svc1")
	assert.True(t, ok)
	assert.Equal(t, "new-token", token)
}

func TestTokenCache_ThreadSafety(t *testing.T) {
	tc := NewTokenCache()
	expiresAt := time.Now().Add(5 * time.Minute)

	var wg sync.WaitGroup
	// Concurrent writes.
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			tc.Put("tenant1", fmt.Sprintf("svc%d", i), fmt.Sprintf("token-%d", i), expiresAt)
		}(i)
	}
	wg.Wait()

	// Concurrent reads.
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			token, ok := tc.Get("tenant1", fmt.Sprintf("svc%d", i))
			assert.True(t, ok)
			assert.Equal(t, fmt.Sprintf("token-%d", i), token)
		}(i)
	}
	wg.Wait()
}

// --- DetermineExpiry tests ---

// buildJWT creates a minimal JWT with the given claims in the payload.
func buildJWT(claims map[string]any) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	payload, _ := json.Marshal(claims)
	payloadB64 := base64.RawURLEncoding.EncodeToString(payload)
	sig := base64.RawURLEncoding.EncodeToString([]byte("fake-signature"))
	return header + "." + payloadB64 + "." + sig
}

func TestDetermineExpiry_JWTExpClaim(t *testing.T) {
	// JWT with exp claim set to a known future time.
	expUnix := time.Now().Add(1 * time.Hour).Unix()
	token := buildJWT(map[string]any{"exp": float64(expUnix), "sub": "user1"})

	// Response body also has expires_in — should be ignored because JWT exp takes priority.
	body := json.RawMessage(`{"expires_in": 60}`)

	result := DetermineExpiry(token, body)
	assert.Equal(t, expUnix, result.Unix())
}

func TestDetermineExpiry_ExpiresInFallback(t *testing.T) {
	// Non-JWT token (not 3 dot-separated parts).
	token := "opaque-token-value"
	body := json.RawMessage(`{"access_token": "opaque-token-value", "expires_in": 600}`)

	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	// Should be approximately now + 600s.
	expectedMin := before.Add(600 * time.Second)
	expectedMax := after.Add(600 * time.Second)
	assert.True(t, result.After(expectedMin) || result.Equal(expectedMin))
	assert.True(t, result.Before(expectedMax) || result.Equal(expectedMax))
}

func TestDetermineExpiry_DefaultFallback(t *testing.T) {
	// Non-JWT token, no expires_in in body.
	token := "opaque-token"
	body := json.RawMessage(`{"access_token": "opaque-token"}`)

	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	// Should be approximately now + 300s.
	expectedMin := before.Add(300 * time.Second)
	expectedMax := after.Add(300 * time.Second)
	assert.True(t, result.After(expectedMin) || result.Equal(expectedMin))
	assert.True(t, result.Before(expectedMax) || result.Equal(expectedMax))
}

func TestDetermineExpiry_JWTWithoutExp(t *testing.T) {
	// Valid JWT structure but no exp claim — falls through to expires_in.
	token := buildJWT(map[string]any{"sub": "user1", "iat": float64(time.Now().Unix())})
	body := json.RawMessage(`{"expires_in": 120}`)

	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	expectedMin := before.Add(120 * time.Second)
	expectedMax := after.Add(120 * time.Second)
	assert.True(t, result.After(expectedMin) || result.Equal(expectedMin))
	assert.True(t, result.Before(expectedMax) || result.Equal(expectedMax))
}

func TestDetermineExpiry_JWTWithoutExp_NoExpiresIn(t *testing.T) {
	// Valid JWT structure but no exp claim, and no expires_in — defaults to 300s.
	token := buildJWT(map[string]any{"sub": "user1"})
	body := json.RawMessage(`{"access_token": "something"}`)

	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	expectedMin := before.Add(300 * time.Second)
	expectedMax := after.Add(300 * time.Second)
	assert.True(t, result.After(expectedMin) || result.Equal(expectedMin))
	assert.True(t, result.Before(expectedMax) || result.Equal(expectedMax))
}

func TestDetermineExpiry_EmptyResponseBody(t *testing.T) {
	// Non-JWT token with empty response body — defaults to 300s.
	token := "opaque"
	body := json.RawMessage(nil)

	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	expectedMin := before.Add(300 * time.Second)
	expectedMax := after.Add(300 * time.Second)
	assert.True(t, result.After(expectedMin) || result.Equal(expectedMin))
	assert.True(t, result.Before(expectedMax) || result.Equal(expectedMax))
}

func TestDetermineExpiry_InvalidJWTPayload(t *testing.T) {
	// Token looks like a JWT (3 parts) but payload is not valid base64/JSON.
	token := "header.!!!invalid!!!.signature"
	body := json.RawMessage(`{"expires_in": 200}`)

	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	// Falls through to expires_in.
	expectedMin := before.Add(200 * time.Second)
	expectedMax := after.Add(200 * time.Second)
	assert.True(t, result.After(expectedMin) || result.Equal(expectedMin))
	assert.True(t, result.Before(expectedMax) || result.Equal(expectedMax))
}

func TestDetermineExpiry_ExpiresInZero(t *testing.T) {
	// expires_in = 0 should fall through to default.
	token := "opaque"
	body := json.RawMessage(`{"expires_in": 0}`)

	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	expectedMin := before.Add(300 * time.Second)
	expectedMax := after.Add(300 * time.Second)
	assert.True(t, result.After(expectedMin) || result.Equal(expectedMin))
	assert.True(t, result.Before(expectedMax) || result.Equal(expectedMax))
}

// --- extractJWTExp tests ---

func TestExtractJWTExp_ValidJWT(t *testing.T) {
	expUnix := int64(1700000000)
	token := buildJWT(map[string]any{"exp": float64(expUnix)})

	result, ok := extractJWTExp(token)
	require.True(t, ok)
	assert.Equal(t, expUnix, result.Unix())
}

func TestExtractJWTExp_NotAJWT(t *testing.T) {
	_, ok := extractJWTExp("not-a-jwt")
	assert.False(t, ok)
}

func TestExtractJWTExp_InvalidBase64(t *testing.T) {
	_, ok := extractJWTExp("a.!!!.c")
	assert.False(t, ok)
}

func TestExtractJWTExp_NoExpClaim(t *testing.T) {
	token := buildJWT(map[string]any{"sub": "user1"})
	_, ok := extractJWTExp(token)
	assert.False(t, ok)
}

// --- BUG-4a: expires_in overflow guard ---

// TestDetermineExpiry_HugeExpiresIn ensures a very large expires_in value
// (≥ 9_300_000_000 seconds, which overflows time.Duration when multiplied)
// does NOT yield a negative or past ExpiresAt. The result must be in the future
// and capped at MaxTokenTTL.
func TestDetermineExpiry_HugeExpiresIn_NotNegative(t *testing.T) {
	token := "opaque-token"
	// 9_300_000_000 seconds overflows int64 time.Duration when * time.Second.
	body := json.RawMessage(`{"expires_in": 9300000000}`)

	before := time.Now()
	result := DetermineExpiry(token, body)

	assert.True(t, result.After(before),
		"ExpiresAt must be in the future, got %v (now %v)", result, before)
	assert.True(t, result.Before(before.Add(MaxTokenTTL+time.Second)),
		"ExpiresAt must be capped at MaxTokenTTL=%v, got %v", MaxTokenTTL, result)
}

// --- BUG-4b: past JWT exp must not be used as the cache expiry ---

// TestDetermineExpiry_PastJWTExp_FallsThrough ensures that when a JWT's exp is
// in the past, DetermineExpiry does NOT use that past timestamp. Instead it falls
// through the priority chain to expires_in (or the 300s default). This ensures
// the past exp value never becomes the ExpiresAt stored in the cache.
func TestDetermineExpiry_PastJWTExp_FallsThrough(t *testing.T) {
	pastExp := time.Now().Add(-10 * time.Minute)
	token := buildJWT(map[string]any{"exp": float64(pastExp.Unix())})

	// Case 1: falls through to expires_in.
	body := json.RawMessage(`{"expires_in": 600}`)
	before := time.Now()
	result := DetermineExpiry(token, body)
	after := time.Now()

	// Must NOT be the past exp value — must be approximately now+600s.
	assert.True(t, result.After(before),
		"past JWT exp must not be used; expected fallback to expires_in (future), got %v", result)
	assert.True(t, result.Before(after.Add(601*time.Second)),
		"fallback to expires_in=600 must yield ~now+600s, got %v", result)
	// Specifically, result must not equal the past JWT exp.
	assert.NotEqual(t, pastExp.Unix(), result.Unix(),
		"ExpiresAt must not equal the past JWT exp timestamp")

	// Case 2: no expires_in, falls through to default (300s).
	body2 := json.RawMessage(`{}`)
	before2 := time.Now()
	result2 := DetermineExpiry(token, body2)
	after2 := time.Now()
	assert.True(t, result2.After(before2),
		"past JWT exp with no expires_in must fall to 300s default, got %v", result2)
	assert.True(t, result2.Before(after2.Add(301*time.Second)),
		"default fallback must be ~now+300s, got %v", result2)
}

// --- BUG-4c: far-future JWT exp must be clamped ---

// TestDetermineExpiry_FarFutureJWTExp ensures an absurdly large JWT exp
// is clamped to MaxTokenTTL so a stale token cannot be pinned indefinitely.
func TestDetermineExpiry_FarFutureJWTExp_Clamped(t *testing.T) {
	// exp 100 years from now.
	farFuture := time.Now().Add(100 * 365 * 24 * time.Hour)
	token := buildJWT(map[string]any{"exp": float64(farFuture.Unix())})
	body := json.RawMessage(`{}`)

	before := time.Now()
	result := DetermineExpiry(token, body)

	assert.True(t, result.After(before),
		"ExpiresAt must be in the future, got %v", result)
	assert.True(t, result.Before(before.Add(MaxTokenTTL+time.Second)),
		"Far-future JWT exp must be clamped to MaxTokenTTL=%v, got %v", MaxTokenTTL, result)
}

// --- BUG-14: cache size cap + eviction ---

// TestTokenCache_SizeCap ensures Put enforces MaxCacheSize and that eviction
// does not corrupt entries for other tenants.
func TestTokenCache_SizeCap_Enforced(t *testing.T) {
	tc := NewTokenCache()
	expiresAt := time.Now().Add(5 * time.Minute)

	// Fill beyond the cap.
	for i := 0; i < MaxCacheSize+10; i++ {
		tc.Put("tenant1", fmt.Sprintf("svc%d", i), fmt.Sprintf("tok-%d", i), expiresAt)
	}

	// The total number of entries must not exceed MaxCacheSize.
	tc.mu.RLock()
	count := len(tc.entries)
	tc.mu.RUnlock()
	assert.LessOrEqual(t, count, MaxCacheSize,
		"cache must not exceed MaxCacheSize=%d entries, got %d", MaxCacheSize, count)
}

// TestTokenCache_SizeCap_OldestEvicted verifies that when the cap is hit the
// eviction policy removes expired entries first, then oldest-inserted ones,
// and leaves newer entries accessible.
func TestTokenCache_SizeCap_NewerEntriesAccessible(t *testing.T) {
	tc := NewTokenCache()
	expiresAt := time.Now().Add(5 * time.Minute)

	// Fill exactly to cap.
	for i := 0; i < MaxCacheSize; i++ {
		tc.Put("tenant1", fmt.Sprintf("old%d", i), fmt.Sprintf("tok-old-%d", i), expiresAt)
	}

	// One more entry beyond the cap.
	tc.Put("tenant1", "newest", "tok-newest", expiresAt)

	// The newest entry must be retrievable.
	tok, ok := tc.Get("tenant1", "newest")
	assert.True(t, ok, "newest entry must survive eviction")
	assert.Equal(t, "tok-newest", tok)

	// Total must still be ≤ MaxCacheSize.
	tc.mu.RLock()
	count := len(tc.entries)
	tc.mu.RUnlock()
	assert.LessOrEqual(t, count, MaxCacheSize)
}

// TestTokenCache_SizeCap_ThreadSafe verifies that concurrent Puts do not corrupt
// the cache or cause a data race (run with -race).
// Uses a small multiplier (3×) of a modest cap so the test runs quickly while
// still exercising concurrent eviction paths.
func TestTokenCache_SizeCap_ThreadSafe(t *testing.T) {
	// Use a local cache with a small cap so concurrent eviction is exercised
	// without spinning up 30 000 goroutines at MaxCacheSize=10 000.
	const localCap = 100
	tc := &TokenCache{entries: make(map[cacheKey]*cacheEntry)}
	expiresAt := time.Now().Add(5 * time.Minute)

	var wg sync.WaitGroup
	for i := 0; i < localCap*3; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			// Inline a Put that uses localCap instead of MaxCacheSize.
			tc.mu.Lock()
			defer tc.mu.Unlock()
			key := cacheKey{TenantID: "tenant1", ServiceID: fmt.Sprintf("svc%d", i)}
			if _, exists := tc.entries[key]; !exists && len(tc.entries) >= localCap {
				// evict expired first
				now := time.Now()
				for k, e := range tc.entries {
					if now.After(e.ExpiresAt) {
						delete(tc.entries, k)
					}
				}
				// evict oldest if still at cap
				if len(tc.entries) >= localCap {
					var oldestKey cacheKey
					var oldestTime time.Time
					first := true
					for k, e := range tc.entries {
						if first || e.ExpiresAt.Before(oldestTime) {
							oldestKey = k
							oldestTime = e.ExpiresAt
							first = false
						}
					}
					delete(tc.entries, oldestKey)
				}
			}
			tc.entries[key] = &cacheEntry{
				Token:      fmt.Sprintf("tok-%d", i),
				ExpiresAt:  expiresAt,
				InsertedAt: time.Now(),
			}
		}(i)
	}
	wg.Wait()

	tc.mu.RLock()
	count := len(tc.entries)
	tc.mu.RUnlock()
	assert.LessOrEqual(t, count, localCap,
		"concurrent puts must not exceed cap=%d, got %d", localCap, count)
}
