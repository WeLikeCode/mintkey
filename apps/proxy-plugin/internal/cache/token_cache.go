// Package cache provides in-memory token caching for the Mintkey Egress Proxy plugin.
//
// The TokenCache stores exchanged bearer tokens keyed by (tenant_id, service_id)
// and determines token expiry using a priority chain: JWT exp → expires_in → 300s default.
//
// Design constraints (Requirements 21.1–21.6):
//   - Thread-safe via sync.RWMutex.
//   - Tokens stored in memory only — no persistence (P-1, S-SEC-1).
//   - Empty on restart.
//   - Get returns token only if expiry > 30s in the future.
//   - DetermineExpiry uses priority: JWT exp → expires_in → 300s default.
//
// BUG-4 fixes:
//   - (4a) expires_in overflow: values are clamped to MaxTokenTTL before the
//     time.Duration multiplication to prevent int64 overflow → negative expiry.
//   - (4b) Past JWT exp: if extractJWTExp returns a time ≤ now, it is treated as
//     invalid and the priority chain falls through to expires_in / default.
//   - (4c) Far-future JWT exp: any exp that is more than MaxTokenTTL from now is
//     clamped to now+MaxTokenTTL so a stale token cannot be pinned indefinitely.
//
// BUG-14 fix:
//   - MaxCacheSize caps the number of cache entries. When a Put would exceed the
//     cap, the eviction policy first removes all fully-expired entries; if the map
//     is still at capacity it removes the single oldest entry (earliest ExpiresAt).
//     All eviction runs under the write-lock, preserving mutex discipline.
//
// Source: design.md §TokenCache; Requirements 21.1–21.6.
package cache

import (
	"encoding/base64"
	"encoding/json"
	"strings"
	"sync"
	"time"
)

const (
	// RefreshBuffer is the time before expiry at which a token is considered
	// near-expiry and a refresh should be triggered.
	RefreshBuffer = 30 * time.Second

	// DefaultExpiry is the fallback token lifetime when neither JWT exp nor
	// expires_in is available.
	DefaultExpiry = 300 * time.Second

	// MaxTokenTTL is the maximum lifetime that DetermineExpiry will assign to
	// any token, regardless of expires_in or JWT exp. Clamping prevents:
	//   - int64 overflow when expires_in is extremely large (BUG-4a)
	//   - a far-future JWT exp pinning a stale/revoked token indefinitely (BUG-4c)
	// Value: 24 hours — well above any real-world token lifetime.
	MaxTokenTTL = 24 * time.Hour

	// MaxCacheSize is the maximum number of entries the TokenCache will hold.
	// When a Put would exceed this limit, expired entries are evicted first;
	// if still at capacity, the entry with the earliest ExpiresAt is removed.
	// 10 000 is a conservative upper bound for (tenant, service) pairs in a
	// single proxy process; beyond this memory growth becomes a DoS risk (BUG-14).
	MaxCacheSize = 10_000
)

// cacheKey uniquely identifies a cached token by tenant and service.
type cacheKey struct {
	TenantID  string
	ServiceID string
}

// cacheEntry holds a cached token, its absolute expiry time, and the wall-clock
// time at which it was inserted (used for oldest-entry eviction in BUG-14 fix).
type cacheEntry struct {
	Token      string
	ExpiresAt  time.Time
	InsertedAt time.Time
}

// TokenCache is an in-memory cache for exchanged bearer tokens.
// Thread-safe. No persistence — empty on process restart.
type TokenCache struct {
	mu      sync.RWMutex
	entries map[cacheKey]*cacheEntry
}

// NewTokenCache creates an empty TokenCache.
func NewTokenCache() *TokenCache {
	return &TokenCache{
		entries: make(map[cacheKey]*cacheEntry),
	}
}

// Get returns the cached token if valid (expiry > 30s from now).
// Returns ("", false) if missing or near-expiry.
func (tc *TokenCache) Get(tenantID, serviceID string) (string, bool) {
	tc.mu.RLock()
	defer tc.mu.RUnlock()

	key := cacheKey{TenantID: tenantID, ServiceID: serviceID}
	entry, ok := tc.entries[key]
	if !ok {
		return "", false
	}

	// Token is considered expired if within the refresh buffer.
	if time.Until(entry.ExpiresAt) <= RefreshBuffer {
		return "", false
	}

	return entry.Token, true
}

// GetForDegradation returns the cached token if it has not fully expired,
// regardless of the 30s refresh buffer. This is used for graceful degradation
// when a token refresh fails — the near-expiry token can still be used until
// it fully expires.
// Returns ("", false) if missing or fully expired.
func (tc *TokenCache) GetForDegradation(tenantID, serviceID string) (string, bool) {
	tc.mu.RLock()
	defer tc.mu.RUnlock()

	key := cacheKey{TenantID: tenantID, ServiceID: serviceID}
	entry, ok := tc.entries[key]
	if !ok {
		return "", false
	}

	// Token is only unusable if fully expired.
	if time.Now().After(entry.ExpiresAt) {
		return "", false
	}

	return entry.Token, true
}

// Put stores a token with the given expiry time.
//
// If the cache already contains MaxCacheSize entries and the incoming key is
// new, Put first evicts all fully-expired entries. If the map is still at
// capacity after that, the single entry with the earliest ExpiresAt is
// removed ("oldest" by lifetime). This keeps the cache bounded under BUG-14.
// All map reads and writes occur under the write-lock.
func (tc *TokenCache) Put(tenantID, serviceID, token string, expiresAt time.Time) {
	tc.mu.Lock()
	defer tc.mu.Unlock()

	key := cacheKey{TenantID: tenantID, ServiceID: serviceID}

	// If we are replacing an existing entry the map size won't grow — skip eviction.
	if _, exists := tc.entries[key]; !exists && len(tc.entries) >= MaxCacheSize {
		tc.evictLocked()
	}

	tc.entries[key] = &cacheEntry{
		Token:      token,
		ExpiresAt:  expiresAt,
		InsertedAt: time.Now(),
	}
}

// evictLocked removes expired entries; if the map is still at capacity it
// removes the single entry with the earliest ExpiresAt. MUST be called under
// tc.mu (write-lock).
func (tc *TokenCache) evictLocked() {
	now := time.Now()

	// Pass 1: remove all fully-expired entries.
	for k, e := range tc.entries {
		if now.After(e.ExpiresAt) {
			delete(tc.entries, k)
		}
	}

	// Pass 2: if still at capacity, remove the entry with the earliest ExpiresAt.
	if len(tc.entries) >= MaxCacheSize {
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

// DetermineExpiry resolves token expiry using the priority chain:
//  1. JWT exp claim (if token is a valid JWT with a future exp field)
//  2. expires_in from response body (seconds from now, clamped to MaxTokenTTL)
//  3. Default 300 seconds from now
//
// BUG-4b: a JWT whose exp is in the past is treated as invalid and falls
// through to the next priority level — it MUST NOT be returned as a valid
// future expiry.
//
// BUG-4a/4c: any computed expiry more than MaxTokenTTL from now is clamped to
// now+MaxTokenTTL to prevent both int64 overflow and indefinite token pinning.
func DetermineExpiry(token string, responseBody json.RawMessage) time.Time {
	now := time.Now()

	// Priority 1: Try to decode the token as a JWT and read the exp claim.
	// BUG-4b: only use exp if it is strictly in the future.
	if expTime, ok := extractJWTExp(token); ok && expTime.After(now) {
		// BUG-4c: clamp absurdly far-future exp to MaxTokenTTL.
		return clampExpiry(now, expTime)
	}

	// Priority 2: Try to read expires_in from the response body.
	// BUG-4a: clamp before multiplying to avoid int64 overflow.
	if expiresIn, ok := extractExpiresInFromBody(responseBody); ok && expiresIn > 0 {
		maxSeconds := int64(MaxTokenTTL / time.Second)
		if expiresIn > maxSeconds {
			expiresIn = maxSeconds
		}
		return now.Add(time.Duration(expiresIn) * time.Second)
	}

	// Priority 3: Default to 300 seconds.
	return now.Add(DefaultExpiry)
}

// clampExpiry returns t if it is within MaxTokenTTL of now, otherwise now+MaxTokenTTL.
func clampExpiry(now, t time.Time) time.Time {
	cap := now.Add(MaxTokenTTL)
	if t.After(cap) {
		return cap
	}
	return t
}

// extractJWTExp attempts to decode the token as a JWT (header.payload.signature)
// and extract the "exp" claim from the payload segment.
// Returns the expiry time and true if successful, or zero time and false otherwise.
func extractJWTExp(token string) (time.Time, bool) {
	// A JWT has exactly 3 dot-separated segments.
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return time.Time{}, false
	}

	// Decode the payload (second segment) from base64url.
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return time.Time{}, false
	}

	// Parse the payload as JSON and look for the "exp" claim.
	var claims map[string]any
	if err := json.Unmarshal(payload, &claims); err != nil {
		return time.Time{}, false
	}

	expVal, ok := claims["exp"]
	if !ok {
		return time.Time{}, false
	}

	// The exp claim should be a numeric value (Unix timestamp).
	switch v := expVal.(type) {
	case float64:
		return time.Unix(int64(v), 0), true
	case json.Number:
		n, err := v.Int64()
		if err != nil {
			return time.Time{}, false
		}
		return time.Unix(n, 0), true
	default:
		return time.Time{}, false
	}
}

// extractExpiresInFromBody attempts to read an "expires_in" field from the
// response body JSON. Returns the value in seconds and true if found.
func extractExpiresInFromBody(body json.RawMessage) (int64, bool) {
	if len(body) == 0 {
		return 0, false
	}

	var obj map[string]any
	if err := json.Unmarshal(body, &obj); err != nil {
		return 0, false
	}

	val, ok := obj["expires_in"]
	if !ok {
		return 0, false
	}

	switch v := val.(type) {
	case float64:
		return int64(v), true
	case json.Number:
		n, err := v.Int64()
		if err != nil {
			return 0, false
		}
		return n, true
	default:
		return 0, false
	}
}
