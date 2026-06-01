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
type JWKSCache struct {
	brokerAddr string
	keys       map[string]ed25519.PublicKey
	mu         sync.RWMutex
	lastFetch  time.Time
	ttl        time.Duration
}

// NewJWKSCache creates a new JWKS cache.
func NewJWKSCache(brokerAddr string) (*JWKSCache, error) {
	cache := &JWKSCache{
		brokerAddr: brokerAddr,
		keys:       make(map[string]ed25519.PublicKey),
		ttl:        5 * time.Minute,
	}

	// Initial fetch
	if err := cache.Refresh(); err != nil {
		return nil, fmt.Errorf("failed to fetch initial JWKS: %w", err)
	}

	return cache, nil
}

// GetKey returns a public key by key ID.
func (c *JWKSCache) GetKey(kid string) (ed25519.PublicKey, error) {
	c.mu.RLock()
	key, ok := c.keys[kid]
	lastFetch := c.lastFetch
	c.mu.RUnlock()

	// If key not found or cache is stale, refresh
	if !ok || time.Since(lastFetch) > c.ttl {
		if err := c.Refresh(); err != nil {
			return nil, fmt.Errorf("failed to refresh JWKS: %w", err)
		}

		c.mu.RLock()
		key, ok = c.keys[kid]
		c.mu.RUnlock()

		if !ok {
			return nil, fmt.Errorf("key %s not found in JWKS", kid)
		}
	}

	return key, nil
}

// Refresh fetches the latest JWKS from the broker.
func (c *JWKSCache) Refresh() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Rate limit refreshes
	if time.Since(c.lastFetch) < 30*time.Second {
		return nil
	}

	url := fmt.Sprintf("http://%s/.well-known/jwks.json", c.brokerAddr)

	resp, err := http.Get(url)
	if err != nil {
		return fmt.Errorf("failed to fetch JWKS: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("JWKS fetch returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read JWKS response: %w", err)
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
		return fmt.Errorf("failed to parse JWKS: %w", err)
	}

	// Parse keys
	newKeys := make(map[string]ed25519.PublicKey)
	for _, jwk := range jwks.Keys {
		if jwk.Kty != "OKP" || jwk.Crv != "Ed25519" {
			continue // Skip non-Ed25519 keys
		}

		// Decode base64url-encoded public key
		pubKeyBytes, err := decodeBase64URL(jwk.X)
		if err != nil {
			return fmt.Errorf("failed to decode key %s: %w", jwk.Kid, err)
		}

		if len(pubKeyBytes) != ed25519.PublicKeySize {
			return fmt.Errorf("invalid public key size for key %s: got %d, want %d", jwk.Kid, len(pubKeyBytes), ed25519.PublicKeySize)
		}

		newKeys[jwk.Kid] = ed25519.PublicKey(pubKeyBytes)
	}

	c.keys = newKeys
	c.lastFetch = time.Now()

	return nil
}

// decodeBase64URL decodes a base64url-encoded string (no padding).
func decodeBase64URL(s string) ([]byte, error) {
	// Add padding if needed
	switch len(s) % 4 {
	case 2:
		s += "=="
	case 3:
		s += "="
	case 1:
		return nil, errors.New("invalid base64url string")
	}

	// Replace URL-safe characters
	s = strings.ReplaceAll(s, "-", "+")
	s = strings.ReplaceAll(s, "_", "/")

	// Decode
	return base64.StdEncoding.DecodeString(s)
}
