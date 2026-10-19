// Package keyloader loads the broker's Ed25519 signing key from a persistent source.
//
// Source: kubernetes-readiness spec; ADR-0033.
package keyloader

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/pem"
	"errors"
	"fmt"
	"os"

	"github.com/mintkey/mintkey/packages/go/ulid"
)

// kidAlphabet is Crockford base32 (ADR-0017.11 wire alphabet).
const kidAlphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// KIDFromPublicKey derives a deterministic key id from the public key:
// "kid_" + the first 26 Crockford base32 characters of sha256(public key).
// The same key therefore keeps the same kid across restarts and replicas, so
// tokens issued before a restart still verify (ADR-0033 D1).
func KIDFromPublicKey(pub ed25519.PublicKey) string {
	sum := sha256.Sum256(pub)
	body := make([]byte, 0, 26)
	var acc uint32
	var bits uint
	for _, b := range sum {
		acc = acc<<8 | uint32(b)
		bits += 8
		for bits >= 5 && len(body) < 26 {
			bits -= 5
			body = append(body, kidAlphabet[(acc>>bits)&31])
		}
		if len(body) == 26 {
			break
		}
	}
	return "kid_" + string(body)
}

// LoadKey returns an Ed25519 private key and its kid.
//
// Source priority:
//  1. File at filePath (raw 32-byte seed or PEM-wrapped seed). When filePath is
//     set but the file is unreadable or not a 32-byte seed, LoadKey fails in
//     every mode; it never falls back silently. The kid is derived from the
//     public key, so it is stable across restarts.
//  2. Dev ephemeral fallback when filePath is empty and env != "production"
//     (random key, random kid).
//
// Vault Adapter path (T-1.0.8+): GetCredential(svcid_broker) — not yet implemented.
func LoadKey(env, filePath string) (ed25519.PrivateKey, string, error) {
	if filePath != "" {
		raw, err := os.ReadFile(filePath)
		if err != nil {
			return nil, "", fmt.Errorf("MINTKEY_BROKER_SIGNING_KEY_FILE is set but unreadable: %w", err)
		}
		seed := raw
		if block, _ := pem.Decode(raw); block != nil {
			seed = block.Bytes
		}
		if len(seed) != ed25519.SeedSize {
			return nil, "", fmt.Errorf("MINTKEY_BROKER_SIGNING_KEY_FILE has the wrong length: got %d bytes, want a %d-byte seed (raw or PEM)", len(seed), ed25519.SeedSize)
		}
		priv := ed25519.NewKeyFromSeed(seed)
		return priv, KIDFromPublicKey(priv.Public().(ed25519.PublicKey)), nil
	}
	if env == "production" {
		return nil, "", errors.New("production requires MINTKEY_BROKER_SIGNING_KEY_FILE to be set")
	}
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, "", err
	}
	kid := ulid.New("kid_")
	return priv, kid, nil
}
