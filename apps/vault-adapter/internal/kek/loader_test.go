package kek_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/kek"
)

// Test: missing KEK source returns error with "KEK source required".
// Source: T-1.0.4 acceptance, design §8, ADR-0003.
func TestLoad_MissingSource(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_KEK_FILE", "")
	t.Setenv("MINTKEY_VAULT_KEK", "")
	t.Setenv("MINTKEY_ENV", "dev")

	_, err := kek.Load()
	if err == nil {
		t.Fatal("expected error for missing KEK source, got nil")
	}
	const want = "KEK source required"
	if err.Error() != want {
		t.Fatalf("error = %q, want %q", err.Error(), want)
	}
}

// Test: keyfile loading from MINTKEY_VAULT_KEK_FILE (32-byte file, mode 0400).
// Source: T-1.0.4 acceptance, design §8.
func TestLoad_Keyfile(t *testing.T) {
	dir := t.TempDir()
	keyfilePath := filepath.Join(dir, "kek")
	key := make([]byte, 32)
	for i := range key {
		key[i] = byte(i + 1)
	}
	if err := os.WriteFile(keyfilePath, key, 0o400); err != nil {
		t.Fatal(err)
	}

	t.Setenv("MINTKEY_VAULT_KEK_FILE", keyfilePath)
	t.Setenv("MINTKEY_VAULT_KEK", "")
	t.Setenv("MINTKEY_ENV", "dev")

	got, err := kek.Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 32 {
		t.Fatalf("key length = %d, want 32", len(got))
	}
	for i, b := range got {
		if b != key[i] {
			t.Fatalf("key[%d] = %d, want %d", i, b, key[i])
		}
	}
}

// Test: keyfile must be exactly 32 bytes.
// Source: ADR-0003 (AES-256-GCM requires 32-byte KEK).
func TestLoad_Keyfile_WrongLength(t *testing.T) {
	dir := t.TempDir()
	keyfilePath := filepath.Join(dir, "kek_short")
	if err := os.WriteFile(keyfilePath, make([]byte, 16), 0o400); err != nil {
		t.Fatal(err)
	}

	t.Setenv("MINTKEY_VAULT_KEK_FILE", keyfilePath)
	t.Setenv("MINTKEY_VAULT_KEK", "")
	t.Setenv("MINTKEY_ENV", "dev")

	_, err := kek.Load()
	if err == nil {
		t.Fatal("expected error for wrong-length key, got nil")
	}
}

// Test: env-var fallback rejected in production mode.
// Source: T-1.0.4 acceptance, ADR-0003.
func TestLoad_EnvVar_RejectedInProduction(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_KEK_FILE", "")
	t.Setenv("MINTKEY_VAULT_KEK", "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899")
	t.Setenv("MINTKEY_ENV", "production")

	_, err := kek.Load()
	if err == nil {
		t.Fatal("expected error for env-var KEK in production, got nil")
	}
}

// Test: env-var fallback allowed in dev mode.
// Source: T-1.0.4 acceptance.
func TestLoad_EnvVar_AllowedInDev(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_KEK_FILE", "")
	// 32 bytes as hex = 64 hex chars
	t.Setenv("MINTKEY_VAULT_KEK", "0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20")
	t.Setenv("MINTKEY_ENV", "dev")

	got, err := kek.Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 32 {
		t.Fatalf("key length = %d, want 32", len(got))
	}
}
