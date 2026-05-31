package googleserviceaccount

import (
	"testing"
	"time"
)

// TestCache_SetAndGet verifies a basic Set+Get round-trip returns a cache hit.
func TestCache_SetAndGet(t *testing.T) {
	c := &Cache{items: make(map[string]cachedToken)}

	c.Set("tenant1", "svc1", "key1", "access-token-abc", 3600)
	tok, ok := c.Get("tenant1", "svc1", "key1")
	if !ok {
		t.Fatal("expected cache hit, got miss")
	}
	if tok != "access-token-abc" {
		t.Errorf("token: got %q, want %q", tok, "access-token-abc")
	}
}

// TestCache_MissUnknownKey verifies Get returns miss for a key never Set.
func TestCache_MissUnknownKey(t *testing.T) {
	c := &Cache{items: make(map[string]cachedToken)}
	_, ok := c.Get("tenant1", "svc1", "key1")
	if ok {
		t.Fatal("expected miss for unknown key, got hit")
	}
}

// TestCache_NearExpiryMiss verifies that when the token will expire within the
// renewalBuffer window, Get returns a miss.
//
// We use the nowFn override to simulate clock advance without sleeping.
// After the test, nowFn is restored to time.Now.
func TestCache_NearExpiryMiss(t *testing.T) {
	origNow := nowFn
	defer func() { nowFn = origNow }()

	c := &Cache{items: make(map[string]cachedToken)}
	// Use real time.Now for Set so expiresAt is meaningful.
	c.Set("tenant1", "svc1", "key1", "expiring-token", 3600)

	// Advance the clock past (expiresAt - renewalBuffer):
	// expiresAt ≈ now + 3600s; renewalBuffer = 5m = 300s.
	// Moving now forward by 3600 - 299 = 3301s ensures nowFn().Add(renewalBuffer) > expiresAt.
	realExp := time.Now().Add(3600 * time.Second)
	nowFn = func() time.Time {
		// Return a time such that now + renewalBuffer > expiresAt.
		return realExp.Add(-renewalBuffer + time.Second)
	}

	_, ok := c.Get("tenant1", "svc1", "key1")
	if ok {
		t.Fatal("expected miss (near expiry), got hit")
	}
}

// TestCache_StillValidHit verifies that a token NOT within the renewal buffer
// is still returned as a hit.
func TestCache_StillValidHit(t *testing.T) {
	origNow := nowFn
	defer func() { nowFn = origNow }()

	c := &Cache{items: make(map[string]cachedToken)}
	c.Set("tenant1", "svc1", "key1", "valid-token", 3600)

	// now + renewalBuffer is well before expiresAt → hit.
	realExp := time.Now().Add(3600 * time.Second)
	nowFn = func() time.Time {
		// now + 5m + 1s < expiresAt  → still inside valid window.
		return realExp.Add(-renewalBuffer - time.Second)
	}

	tok, ok := c.Get("tenant1", "svc1", "key1")
	if !ok {
		t.Fatal("expected cache hit, got miss")
	}
	if tok != "valid-token" {
		t.Errorf("token: got %q", tok)
	}
}

// TestCache_Invalidate verifies that Set → Invalidate → Get returns miss.
func TestCache_Invalidate(t *testing.T) {
	c := &Cache{items: make(map[string]cachedToken)}
	c.Set("tenant1", "svc1", "key1", "some-token", 3600)

	c.Invalidate("tenant1", "svc1", "key1")

	_, ok := c.Get("tenant1", "svc1", "key1")
	if ok {
		t.Fatal("expected miss after Invalidate, got hit")
	}
}

// TestCache_InvalidateDoesNotAffectOtherKeys verifies that Invalidate removes
// only the targeted key and leaves others intact.
func TestCache_InvalidateDoesNotAffectOtherKeys(t *testing.T) {
	c := &Cache{items: make(map[string]cachedToken)}
	c.Set("tenant1", "svc1", "key1", "token-1", 3600)
	c.Set("tenant1", "svc1", "key2", "token-2", 3600)

	c.Invalidate("tenant1", "svc1", "key1")

	_, ok := c.Get("tenant1", "svc1", "key1")
	if ok {
		t.Error("key1 should have been invalidated")
	}
	_, ok = c.Get("tenant1", "svc1", "key2")
	if !ok {
		t.Error("key2 should still be present after invalidating key1")
	}
}

// TestGlobalCacheDocComment just ensures GlobalCache is the exported package var
// (compile-time check; no runtime assertion needed).
func TestGlobalCacheDocComment(t *testing.T) {
	if GlobalCache == nil {
		t.Fatal("GlobalCache must not be nil")
	}
}
