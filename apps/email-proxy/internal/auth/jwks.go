// Package auth handles JWT validation for the Email Proxy.
//
// JWS-Ed25519 tokens issued by the Mintkey broker are validated here.
// JWKS is fetched from the broker JWKS URL and cached per ADR-0016.2:
// on an unknown kid, the cache is force-refreshed once before failing.
package auth

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// minForceRefreshInterval is the minimum time between ForceRefresh calls.
// Prevents a spray of unknown-kid tokens from amplifying outbound JWKS fetches
// (one GET per request → DoS against the JWKS endpoint).
const minForceRefreshInterval = 5 * time.Second

// JWKSCache caches JWKS (JSON Web Key Set) from the broker.
// Thread-safe; the first network fetch is deferred until GetKey is called.
type JWKSCache struct {
	jwksURL          string
	keys             map[string]ed25519.PublicKey
	mu               sync.RWMutex
	lastFetch        time.Time
	lastForceRefresh time.Time // separate rate-limit for ForceRefresh calls
	ttl              time.Duration
}

// NewJWKSCache creates a new JWKS cache for the given full URL.
// The first network fetch is deferred until GetKey is called.
func NewJWKSCache(jwksURL string) (*JWKSCache, error) {
	if jwksURL == "" {
		return nil, errors.New("jwksURL must not be empty")
	}
	return &JWKSCache{
		jwksURL: jwksURL,
		keys:    make(map[string]ed25519.PublicKey),
		ttl:     5 * time.Minute,
	}, nil
}

// GetKey returns the Ed25519 public key for the given key ID.
// Per ADR-0016.2: if the kid is unknown, the cache is force-refreshed once
// (bypassing the rate-limit window) before giving up.
func (c *JWKSCache) GetKey(kid string) (ed25519.PublicKey, error) {
	// Fast path: key in cache and cache is fresh.
	c.mu.RLock()
	key, ok := c.keys[kid]
	lastFetch := c.lastFetch
	c.mu.RUnlock()

	if ok && time.Since(lastFetch) <= c.ttl {
		return key, nil
	}

	// Cache miss or stale — refresh.
	if err := c.Refresh(); err != nil {
		return nil, fmt.Errorf("jwks: refresh failed: %w", err)
	}

	c.mu.RLock()
	key, ok = c.keys[kid]
	c.mu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("jwks: key %q not found after refresh", kid)
	}
	return key, nil
}

// ForceRefresh triggers an out-of-band JWKS fetch, used by the unknown-kid
// path (ADR-0016.2). A dedicated 5-second rate-limit guards against an
// attacker spraying random kids triggering one outbound GET per request.
// If a force-refresh happened within the last 5 seconds, this is a no-op.
func (c *JWKSCache) ForceRefresh() error {
	c.mu.Lock()
	if time.Since(c.lastForceRefresh) < minForceRefreshInterval {
		c.mu.Unlock()
		return nil // throttled; a recent force-refresh already pulled fresh keys
	}
	// Reset lastFetch so Refresh() executes even within the 30s window.
	c.lastFetch = time.Time{}
	c.lastForceRefresh = time.Now()
	c.mu.Unlock()
	return c.Refresh()
}

// Refresh fetches the latest JWKS from the broker. Calls within the
// 30-second rate-limit window are silently skipped.
func (c *JWKSCache) Refresh() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Rate-limit: skip if last fetch was < 30s ago.
	if !c.lastFetch.IsZero() && time.Since(c.lastFetch) < 30*time.Second {
		return nil
	}

	resp, err := http.Get(c.jwksURL) //nolint:gosec // URL is operator-controlled config, not user input
	if err != nil {
		return fmt.Errorf("jwks: GET %s: %w", c.jwksURL, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("jwks: GET %s returned status %d", c.jwksURL, resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("jwks: read response: %w", err)
	}

	var jwks struct {
		Keys []struct {
			Kid string `json:"kid"`
			Kty string `json:"kty"`
			Crv string `json:"crv"`
			X   string `json:"x"`
		} `json:"keys"`
	}

	if err := json.Unmarshal(body, &jwks); err != nil {
		return fmt.Errorf("jwks: parse response: %w", err)
	}

	newKeys := make(map[string]ed25519.PublicKey, len(jwks.Keys))
	for _, jwk := range jwks.Keys {
		if jwk.Kty != "OKP" || jwk.Crv != "Ed25519" {
			continue // skip non-Ed25519 keys
		}
		pubKeyBytes, err := decodeBase64URL(jwk.X)
		if err != nil {
			return fmt.Errorf("jwks: decode key %q: %w", jwk.Kid, err)
		}
		if len(pubKeyBytes) != ed25519.PublicKeySize {
			return fmt.Errorf("jwks: key %q has invalid size %d (want %d)", jwk.Kid, len(pubKeyBytes), ed25519.PublicKeySize)
		}
		newKeys[jwk.Kid] = ed25519.PublicKey(pubKeyBytes)
	}

	c.keys = newKeys
	c.lastFetch = time.Now()
	return nil
}

// decodeBase64URL decodes a base64url-encoded string (no padding).
func decodeBase64URL(s string) ([]byte, error) {
	switch len(s) % 4 {
	case 2:
		s += "=="
	case 3:
		s += "="
	case 1:
		return nil, errors.New("invalid base64url string: length mod 4 == 1")
	}
	s = strings.ReplaceAll(s, "-", "+")
	s = strings.ReplaceAll(s, "_", "/")
	return base64.StdEncoding.DecodeString(s)
}
