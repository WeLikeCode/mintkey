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
	"pgregory.net/rapid"
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
//
// CO-5 fix: this test now drives the REAL Put/eviction rather than reimplementing
// eviction logic inline. We use 3× a modest key count so concurrent eviction is
// exercised without spinning up tens-of-thousands of goroutines. The real Put
// enforces MaxCacheSize via evictLocked; we assert the cap is never breached.
func TestTokenCache_SizeCap_ThreadSafe(t *testing.T) {
	tc := NewTokenCache()
	expiresAt := time.Now().Add(5 * time.Minute)

	// 300 unique keys → 3× a 100-entry window, enough to trigger eviction repeatedly
	// while keeping the test fast (no reimplementation of the eviction logic).
	const keys = 300

	var wg sync.WaitGroup
	for i := 0; i < keys; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			tc.Put("tenant1", fmt.Sprintf("svc%d", i), fmt.Sprintf("tok-%d", i), expiresAt)
		}(i)
	}
	wg.Wait()

	tc.mu.RLock()
	count := len(tc.entries)
	tc.mu.RUnlock()
	assert.LessOrEqual(t, count, MaxCacheSize,
		"concurrent puts must not exceed MaxCacheSize=%d, got %d", MaxCacheSize, count)
}

// =============================================================================
// Property-based tests (pgregory.net/rapid)
// =============================================================================

// --- 7.5 Unit: empty on construction + no persistence ---

// TestTokenCache_EmptyOnConstruction_Unit explicitly validates that a freshly
// created cache has no entries (Requirement 21.5, 21.6).
func TestTokenCache_NoPersistence_NewInstanceIsEmpty(t *testing.T) {
	// Create, store a token, discard the cache, create a new one.
	tc1 := NewTokenCache()
	tc1.Put("t1", "s1", "secret", time.Now().Add(10*time.Minute))

	// New instance must be completely empty — no persistence.
	tc2 := NewTokenCache()
	token, ok := tc2.Get("t1", "s1")
	assert.False(t, ok, "new cache must not inherit entries from a previous instance")
	assert.Empty(t, token)

	tc2.mu.RLock()
	count := len(tc2.entries)
	tc2.mu.RUnlock()
	assert.Equal(t, 0, count, "new cache must have zero entries on construction")
}

// --- Property 7: Cache keyed retrieval ---

// TestCacheKeyedRetrieval — Property 7.
//
// For any set of (tenant_id, service_id) pairs with stored tokens, retrieving
// by a specific key returns ONLY that key's token; no cross-key bleed occurs.
//
// Discriminating power: if Put stored under the wrong composite key (e.g. only
// tenant_id), or Get looked up only by serviceID, a different key's token would
// be returned, falsifying the equality assertion.
func TestCacheKeyedRetrieval(t *testing.T) {
	rapid.Check(t, func(rt *rapid.T) {
		// Generate 1–10 distinct (tenantID, serviceID) pairs.
		n := rapid.IntRange(1, 10).Draw(rt, "n")

		type kv struct {
			tenant  string
			service string
			token   string
		}
		pairs := make([]kv, n)
		seen := make(map[string]bool)

		for i := 0; i < n; i++ {
			var tid, sid string
			// Ensure unique composite keys.
			for {
				tid = rapid.StringMatching(`[a-z]{1,8}`).Draw(rt, fmt.Sprintf("tid%d", i))
				sid = rapid.StringMatching(`[a-z]{1,8}`).Draw(rt, fmt.Sprintf("sid%d", i))
				composite := tid + "|" + sid
				if !seen[composite] {
					seen[composite] = true
					break
				}
			}
			tok := rapid.StringMatching(`[a-zA-Z0-9]{4,20}`).Draw(rt, fmt.Sprintf("tok%d", i))
			pairs[i] = kv{tid, sid, tok}
		}

		tc := NewTokenCache()
		expiresAt := time.Now().Add(10 * time.Minute) // well beyond 30s buffer
		for _, p := range pairs {
			tc.Put(p.tenant, p.service, p.token, expiresAt)
		}

		// Each key must return exactly its own token; no other key's token.
		for i, p := range pairs {
			got, ok := tc.Get(p.tenant, p.service)
			if !ok {
				rt.Fatalf("pair[%d] (%s,%s): expected hit, got miss", i, p.tenant, p.service)
			}
			if got != p.token {
				rt.Fatalf("pair[%d] (%s,%s): expected token %q, got %q (cross-key bleed)",
					i, p.tenant, p.service, p.token, got)
			}
		}
	})
}

// --- Property 8: Expiry detection priority chain ---

// TestExpiryDetectionPriority — Property 8.
//
// DetermineExpiry follows the priority: JWT exp → expires_in → 300s default.
// FIX-4 semantics apply: exp must be future and ≤ now+MaxTokenTTL.
//
// Discriminating power:
//   - If JWT exp were ignored and expires_in used instead, the result would
//     differ from exp by the gap between exp and now+expires_in.
//   - If expires_in were ignored and the default used, branch 2 would return
//     now+300 instead of now+expires_in.
//   - If the default branch returned now+0, branch 3 would fail.
func TestExpiryDetectionPriority(t *testing.T) {
	rapid.Check(t, func(rt *rapid.T) {
		branch := rapid.IntRange(1, 3).Draw(rt, "branch")

		switch branch {
		case 1:
			// Branch 1: valid JWT with future exp within [1s, MaxTokenTTL].
			// DetermineExpiry must return clamp(exp), which equals exp when exp ≤ now+MaxTokenTTL.
			offsetSec := rapid.Int64Range(1, int64(MaxTokenTTL/time.Second)).Draw(rt, "offsetSec")
			futureExp := time.Now().Add(time.Duration(offsetSec) * time.Second)
			token := buildJWT(map[string]any{"exp": float64(futureExp.Unix()), "sub": "u"})
			// Body also has expires_in to confirm it is NOT used.
			body := json.RawMessage(`{"expires_in": 60}`)

			before := time.Now()
			result := DetermineExpiry(token, body)

			// Result must equal futureExp (clamped). Since offsetSec ≤ MaxTokenTTL,
			// clamp does not change it — result.Unix() must equal futureExp.Unix().
			if result.Unix() != futureExp.Unix() {
				rt.Fatalf("branch1: JWT exp priority: expected %v, got %v (delta %v)",
					futureExp.Unix(), result.Unix(), result.Unix()-futureExp.Unix())
			}
			// Sanity: must be in the future.
			if !result.After(before) {
				rt.Fatalf("branch1: result %v must be after now %v", result, before)
			}

		case 2:
			// Branch 2: non-JWT token + expires_in in body. No JWT exp to parse.
			expiresInSec := rapid.Int64Range(1, int64(MaxTokenTTL/time.Second)).Draw(rt, "expiresInSec")
			token := "opaque-" + rapid.StringMatching(`[a-z]{4}`).Draw(rt, "suffix")
			body, _ := json.Marshal(map[string]any{"expires_in": expiresInSec})

			before := time.Now()
			result := DetermineExpiry(token, json.RawMessage(body))
			after := time.Now()

			// Must be ≈ now + expiresInSec (within a 2s window for test jitter).
			low := before.Add(time.Duration(expiresInSec) * time.Second)
			high := after.Add(time.Duration(expiresInSec) * time.Second)
			if result.Before(low) || result.After(high) {
				rt.Fatalf("branch2: expires_in=%d: expected result in [%v, %v], got %v",
					expiresInSec, low, high, result)
			}

		case 3:
			// Branch 3: non-JWT token, no expires_in → 300s default.
			token := "opaque-" + rapid.StringMatching(`[a-z]{4}`).Draw(rt, "suffix")
			body := json.RawMessage(`{}`)

			before := time.Now()
			result := DetermineExpiry(token, body)
			after := time.Now()

			low := before.Add(DefaultExpiry)
			high := after.Add(DefaultExpiry)
			if result.Before(low) || result.After(high) {
				rt.Fatalf("branch3: default 300s: expected result in [%v, %v], got %v",
					low, high, result)
			}
		}
	})
}

// --- Property 9: Cache hit/refresh threshold at 30 seconds ---

// TestCacheThreshold — Property 9.
//
// TokenCache.Get returns the token if and only if expiry > 30s in the future;
// otherwise it signals a cache miss.
//
// Discriminating power: if the threshold were 0s (no buffer), tokens with
// 1s–30s remaining would incorrectly return hits. If the threshold were 60s,
// tokens with 31s–60s remaining would incorrectly return misses.
func TestCacheThreshold(t *testing.T) {
	rapid.Check(t, func(rt *rapid.T) {
		// offsetSec: range −60 to +600 seconds from now.
		// Values > 30  → cache hit expected.
		// Values ≤ 30  → cache miss expected.
		offsetSec := rapid.Int64Range(-60, 600).Draw(rt, "offsetSec")
		expiresAt := time.Now().Add(time.Duration(offsetSec) * time.Second)

		tc := NewTokenCache()
		const tok = "some-token"
		tc.Put("t", "s", tok, expiresAt)

		got, ok := tc.Get("t", "s")

		remaining := time.Until(expiresAt)
		shouldHit := remaining > RefreshBuffer // > 30s

		if shouldHit {
			if !ok {
				rt.Fatalf("offsetSec=%d (remaining=%v > 30s): expected hit, got miss",
					offsetSec, remaining)
			}
			if got != tok {
				rt.Fatalf("offsetSec=%d: expected token %q, got %q", offsetSec, tok, got)
			}
		} else {
			if ok {
				rt.Fatalf("offsetSec=%d (remaining=%v ≤ 30s): expected miss, got hit (token=%q)",
					offsetSec, remaining, got)
			}
		}
	})
}
