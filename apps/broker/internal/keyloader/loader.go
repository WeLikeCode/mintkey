// Package keyloader loads the broker's Ed25519 signing key from a persistent source.
//
// Source: kubernetes-readiness spec; ADR-0030.
package keyloader

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/pem"
	"errors"
	"os"

	"github.com/mintkey/mintkey/packages/go/ulid"
)

// LoadKey returns an Ed25519 private key and its kid.
//
// Source priority:
//  1. File at filePath (raw 32-byte seed or PEM-wrapped seed).
//  2. Dev ephemeral fallback when filePath is empty and env != "production".
//
// Vault Adapter path (T-1.0.8+): GetCredential(svcid_broker) — not yet implemented.
func LoadKey(env, filePath string) (ed25519.PrivateKey, string, error) {
	if filePath != "" {
		raw, err := os.ReadFile(filePath)
		if err == nil {
			seed := raw
			if block, _ := pem.Decode(raw); block != nil {
				seed = block.Bytes
			}
			if len(seed) == ed25519.SeedSize {
				priv := ed25519.NewKeyFromSeed(seed)
				kid := ulid.New("kid_")
				return priv, kid, nil
			}
		}
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
