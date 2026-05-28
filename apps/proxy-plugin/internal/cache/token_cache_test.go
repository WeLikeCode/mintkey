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
