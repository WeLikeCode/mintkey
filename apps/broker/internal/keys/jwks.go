// Package keys manages the broker's Ed25519 signing key ring and JWKS endpoint.
//
// Source: design §7; ADR-0006; ADR-0016.2; T-1.0.5.
package keys

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"sync"
)

// KeyRing holds one or more Ed25519 public keys (active + retiring during overlap).
type KeyRing struct {
	mu   sync.RWMutex
	keys []jwkEntry
}

type jwkEntry struct {
	kid string
	pub ed25519.PublicKey
}

// NewKeyRing creates an empty KeyRing.
func NewKeyRing() *KeyRing {
	return &KeyRing{}
}

// Add appends a public key with its kid to the ring.
func (r *KeyRing) Add(kid string, pub ed25519.PublicKey) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.keys = append(r.keys, jwkEntry{kid: kid, pub: pub})
}

type jwkSet struct {
	Keys []jwkPublic `json:"keys"`
}

type jwkPublic struct {
	Kty string `json:"kty"`
	Crv string `json:"crv"`
	Use string `json:"use"`
	Kid string `json:"kid"`
	X   string `json:"x"` // base64url-encoded public key bytes (RFC 8037)
}

// JWKSHandler returns an http.Handler for GET /.well-known/jwks.json.
// All keys in the ring are included (active + retiring overlap).
// Source: Req 6 AC9; ADR-0006; T-1.0.5.
func JWKSHandler(ring *KeyRing) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ring.mu.RLock()
		set := jwkSet{Keys: make([]jwkPublic, 0, len(ring.keys))}
		for _, e := range ring.keys {
			set.Keys = append(set.Keys, jwkPublic{
				Kty: "OKP",
				Crv: "Ed25519",
				Use: "sig",
				Kid: e.kid,
				X:   base64.RawURLEncoding.EncodeToString(e.pub),
			})
		}
		ring.mu.RUnlock()

		body, err := json.Marshal(set)
		if err != nil {
			http.Error(w, "internal error", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "public, max-age=300")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(body)
	})
}
