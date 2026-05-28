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
)

// cacheKey uniquely identifies a cached token by tenant and service.
type cacheKey struct {
	TenantID  string
	ServiceID string
}

// cacheEntry holds a cached token and its absolute expiry time.
type cacheEntry struct {
	Token     string
	ExpiresAt time.Time
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
func (tc *TokenCache) Put(tenantID, serviceID, token string, expiresAt time.Time) {
	tc.mu.Lock()
	defer tc.mu.Unlock()

	key := cacheKey{TenantID: tenantID, ServiceID: serviceID}
	tc.entries[key] = &cacheEntry{
		Token:     token,
		ExpiresAt: expiresAt,
	}
}

// DetermineExpiry resolves token expiry using the priority chain:
//  1. JWT exp claim (if token is a valid JWT with an exp field)
//  2. expires_in from response body (seconds from now)
//  3. Default 300 seconds from now
func DetermineExpiry(token string, responseBody json.RawMessage) time.Time {
	now := time.Now()

	// Priority 1: Try to decode the token as a JWT and read the exp claim.
	if expTime, ok := extractJWTExp(token); ok {
		return expTime
	}

	// Priority 2: Try to read expires_in from the response body.
	if expiresIn, ok := extractExpiresInFromBody(responseBody); ok && expiresIn > 0 {
		return now.Add(time.Duration(expiresIn) * time.Second)
	}

	// Priority 3: Default to 300 seconds.
	return now.Add(DefaultExpiry)
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
