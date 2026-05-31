// Package store — backend selector for the Vault Adapter credential store.
//
// Backend is the abstraction implemented by both *Store (SQLite) and
// *PostgresStore (Postgres). NewFromEnv inspects MINTKEY_VAULT_BACKEND and
// constructs the appropriate backend. Default is "postgres" per owner decision
// (ADR-0003 §C3).
//
// Source: design §8; ADR-0003; T-1.3.3 (C3).
package store

import (
	"context"
	"fmt"
	"os"
	"strings"
)

// Backend is the abstraction shared by the SQLite and Postgres credential
// stores. Both *Store (sqlite.go) and *PostgresStore (postgres.go) satisfy
// this interface without any modifications to those files.
type Backend interface {
	Put(ctx context.Context, rec CredentialRecord) (uint32, error)
	Get(ctx context.Context, tenantID, serviceID string, keyVersion uint32) (*CredentialRecord, error)
	Revoke(ctx context.Context, tenantID, serviceID string, keyVersion uint32) error
	ListVersions(ctx context.Context, tenantID, serviceID string, afterKeyVersion, limit uint32) ([]CredentialRecord, error)
	Close() error
}

// NewFromEnv constructs the credential store backend selected by
// MINTKEY_VAULT_BACKEND. Accepted values:
//
//   - "postgres" (default) — requires MINTKEY_VAULT_PG_DSN
//   - "sqlite"             — requires MINTKEY_VAULT_FILE_PATH
//
// An empty MINTKEY_VAULT_BACKEND defaults to "postgres".
func NewFromEnv(ctx context.Context) (Backend, error) {
	backend := strings.ToLower(strings.TrimSpace(os.Getenv("MINTKEY_VAULT_BACKEND")))
	if backend == "" {
		backend = "postgres" // default per owner decision
	}
	switch backend {
	case "postgres":
		dsn := os.Getenv("MINTKEY_VAULT_PG_DSN")
		if dsn == "" {
			return nil, fmt.Errorf("MINTKEY_VAULT_BACKEND=postgres requires MINTKEY_VAULT_PG_DSN")
		}
		return NewPostgres(ctx, dsn)
	case "sqlite":
		path := os.Getenv("MINTKEY_VAULT_FILE_PATH")
		if path == "" {
			return nil, fmt.Errorf("MINTKEY_VAULT_BACKEND=sqlite requires MINTKEY_VAULT_FILE_PATH")
		}
		return New(path)
	default:
		return nil, fmt.Errorf("unknown MINTKEY_VAULT_BACKEND=%q (expected 'postgres' or 'sqlite')", backend)
	}
}
