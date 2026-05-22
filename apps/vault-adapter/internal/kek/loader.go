// Package kek loads and validates the Key Encryption Key (KEK) from
// either a keyfile or an environment variable (dev only).
//
// Source: design §8 security invariants; ADR-0003; T-1.0.4.
package kek

import (
	"encoding/hex"
	"errors"
	"fmt"
	"os"
)

// Load returns a 32-byte AES-256 KEK.
//
// Priority:
//  1. MINTKEY_VAULT_KEK_FILE — file path; must be 32 bytes, mode 0400.
//  2. MINTKEY_VAULT_KEK     — hex-encoded 32-byte value; REJECTED in MINTKEY_ENV=production.
//
// Returns an error with text "KEK source required" when neither is set.
func Load() ([]byte, error) {
	keyfilePath := os.Getenv("MINTKEY_VAULT_KEK_FILE")
	envKey := os.Getenv("MINTKEY_VAULT_KEK")
	env := os.Getenv("MINTKEY_ENV")

	switch {
	case keyfilePath != "":
		return loadFromFile(keyfilePath)
	case envKey != "":
		if env == "production" {
			return nil, errors.New(
				"MINTKEY_VAULT_KEK env-var KEK is not allowed in production; use MINTKEY_VAULT_KEK_FILE",
			)
		}
		return loadFromHex(envKey)
	default:
		return nil, errors.New("KEK source required")
	}
}

func loadFromFile(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("KEK keyfile: %w", err)
	}
	if len(data) != 32 {
		return nil, fmt.Errorf("KEK keyfile: must be exactly 32 bytes, got %d", len(data))
	}
	return data, nil
}

func loadFromHex(s string) ([]byte, error) {
	data, err := hex.DecodeString(s)
	if err != nil {
		return nil, fmt.Errorf("MINTKEY_VAULT_KEK: invalid hex: %w", err)
	}
	if len(data) != 32 {
		return nil, fmt.Errorf("MINTKEY_VAULT_KEK: must decode to 32 bytes, got %d", len(data))
	}
	return data, nil
}
