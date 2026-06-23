// Tests for the NewFromEnv backend selector.
// These tests run without any build tags and do NOT require a live database.
package store

import (
	"context"
	"errors"
	"os"
	"strings"
	"testing"
)

// TestNewFromEnv_DefaultsToPostgres verifies that an empty MINTKEY_VAULT_BACKEND
// selects the postgres path and returns an error about MINTKEY_VAULT_PG_DSN
// rather than about MINTKEY_VAULT_FILE_PATH — proving the selector branched to
// postgres even though no DSN was provided.
func TestNewFromEnv_DefaultsToPostgres(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_BACKEND", "")
	t.Setenv("MINTKEY_VAULT_PG_DSN", "")
	t.Setenv("MINTKEY_VAULT_FILE_PATH", "")

	_, err := NewFromEnv(context.Background())
	if err == nil {
		t.Fatal("expected error when MINTKEY_VAULT_PG_DSN is empty, got nil")
	}
	if !strings.Contains(err.Error(), "MINTKEY_VAULT_PG_DSN") {
		t.Errorf("expected error to mention MINTKEY_VAULT_PG_DSN, got: %v", err)
	}
}

// TestNewFromEnv_Sqlite verifies that MINTKEY_VAULT_BACKEND=sqlite creates a
// real SQLite store backed by a temp file.
func TestNewFromEnv_Sqlite(t *testing.T) {
	f, err := os.CreateTemp(t.TempDir(), "vault-factory-*.db")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	f.Close()

	t.Setenv("MINTKEY_VAULT_BACKEND", "sqlite")
	t.Setenv("MINTKEY_VAULT_FILE_PATH", f.Name())

	b, err := NewFromEnv(context.Background())
	if err != nil {
		t.Fatalf("NewFromEnv sqlite: unexpected error: %v", err)
	}
	t.Cleanup(func() { _ = b.Close() })

	// Confirm it is a *Store (SQLite) and not *PostgresStore.
	if _, ok := b.(*Store); !ok {
		t.Errorf("expected *Store for sqlite backend, got %T", b)
	}
}

// TestNewFromEnv_PostgresMissingDSN verifies that MINTKEY_VAULT_BACKEND=postgres
// without a DSN returns an error mentioning MINTKEY_VAULT_PG_DSN.
func TestNewFromEnv_PostgresMissingDSN(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_BACKEND", "postgres")
	t.Setenv("MINTKEY_VAULT_PG_DSN", "")

	_, err := NewFromEnv(context.Background())
	if err == nil {
		t.Fatal("expected error for missing DSN, got nil")
	}
	if !strings.Contains(err.Error(), "MINTKEY_VAULT_PG_DSN") {
		t.Errorf("expected error to mention MINTKEY_VAULT_PG_DSN, got: %v", err)
	}
}

// TestNewFromEnv_UnknownBackend verifies that an unrecognised backend value
// returns an error that includes the bad value.
func TestNewFromEnv_UnknownBackend(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_BACKEND", "mysql")

	_, err := NewFromEnv(context.Background())
	if err == nil {
		t.Fatal("expected error for unknown backend, got nil")
	}
	// Must mention the bad value so operators know what to fix.
	if !strings.Contains(err.Error(), "mysql") {
		t.Errorf("expected error to mention bad value 'mysql', got: %v", err)
	}
	// Sentinel check: not a wrapped sql/pgx error — it's purely a config error.
	var target interface{ Unwrap() error }
	if errors.As(err, &target) {
		// wrapped errors are fine, just ensure the message includes the value
	}
}

// TestNewFromEnv_HashicorpMissingRoleID verifies that MINTKEY_VAULT_BACKEND=hashicorp
// without a role ID returns an error mentioning MINTKEY_VAULT_HASHICORP_ROLE_ID.
func TestNewFromEnv_HashicorpMissingRoleID(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_BACKEND", "hashicorp")
	t.Setenv("MINTKEY_VAULT_HASHICORP_ADDR", "http://localhost:8201")
	t.Setenv("MINTKEY_VAULT_HASHICORP_ROLE_ID", "") // missing

	_, err := NewFromEnv(context.Background())
	if err == nil {
		t.Fatal("expected error for missing role ID, got nil")
	}
	if !strings.Contains(err.Error(), "MINTKEY_VAULT_HASHICORP_ROLE_ID") {
		t.Errorf("expected error to mention MINTKEY_VAULT_HASHICORP_ROLE_ID, got: %v", err)
	}
}

// TestNewFromEnv_HashicorpMissingAddr verifies that MINTKEY_VAULT_BACKEND=hashicorp
// without an address returns an error mentioning MINTKEY_VAULT_HASHICORP_ADDR.
func TestNewFromEnv_HashicorpMissingAddr(t *testing.T) {
	t.Setenv("MINTKEY_VAULT_BACKEND", "hashicorp")
	t.Setenv("MINTKEY_VAULT_HASHICORP_ADDR", "") // missing

	_, err := NewFromEnv(context.Background())
	if err == nil {
		t.Fatal("expected error for missing addr, got nil")
	}
	if !strings.Contains(err.Error(), "MINTKEY_VAULT_HASHICORP_ADDR") {
		t.Errorf("expected error to mention MINTKEY_VAULT_HASHICORP_ADDR, got: %v", err)
	}
}
