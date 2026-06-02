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

// JWKSCache caches JWKS (JSON Web Key Set) from the broker.
// Thread-safe; the first network fetch is deferred until GetKey is called.
type JWKSCache struct {
	jwksURL   string
	keys      map[string]ed25519.PublicKey
	mu        sync.RWMutex
	lastFetch time.Time
	ttl       time.Duration
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

// ForceRefresh bypasses the rate-limit window and unconditionally fetches
// the JWKS. Used by the unknown-kid path (ADR-0016.2).
func (c *JWKSCache) ForceRefresh() error {
	c.mu.Lock()
	// Reset lastFetch so Refresh() skips its rate-limit guard.
	c.lastFetch = time.Time{}
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
