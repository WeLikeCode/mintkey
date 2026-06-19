// agent_secret.go — AgentSecretStore interface and Postgres implementation (ADR-0025).
//
// AgentSecretsVault is a sibling gRPC service to VaultAdapter, keyed by
// (tenant_id, secret_id) instead of (tenant_id, service_id, key_version).
// It reuses the same encryption envelope (crypto.Seal/Open) and the same
// per-transaction set_config('app.current_tenant', …) + pg_advisory_xact_lock
// RLS discipline.
//
// Table: vault.agent_secrets
//
//	secret_id   UUID PK
//	tenant_id   UUID NOT NULL
//	key_version INTEGER NOT NULL
//	wrapped_dek BYTEA
//	enc_payload BYTEA
//	created_at  TIMESTAMPTZ
//	updated_at  TIMESTAMPTZ
//
// The table is created by Liquibase changelog 027 (written in parallel).
// This file only does data access; schema ownership stays with Liquibase.
package store

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

// AgentSecretRecord is the row shape for vault.agent_secrets.
type AgentSecretRecord struct {
	SecretID   string
	TenantID   string
	KeyVersion int32
	WrappedDEK []byte
	EncPayload []byte
	CreatedAt  time.Time
	UpdatedAt  time.Time
}

// AgentSecretStore is the data-access interface for vault.agent_secrets.
// It is satisfied by *PostgresStore (Postgres backend); the SQLite backend
// returns codes.Unimplemented — see package server for the gRPC layer.
type AgentSecretStore interface {
	// PutAgentSecret upserts the encrypted blob for (tenant_id, secret_id).
	// On insert sets created_at = updated_at = now; on update only advances updated_at.
	// key_version must be >= 1 (assigned by the caller before the RPC).
	PutAgentSecret(ctx context.Context, rec AgentSecretRecord) error

	// GetAgentSecret returns the encrypted blob for (tenant_id, secret_id).
	// Returns (nil, sql.ErrNoRows-wrapped error) when not found.
	GetAgentSecret(ctx context.Context, tenantID, secretID string) (*AgentSecretRecord, error)

	// DeleteAgentSecret removes the row for (tenant_id, secret_id).
	// Idempotent: no error when the row is already absent.
	DeleteAgentSecret(ctx context.Context, tenantID, secretID string) error
}

// PutAgentSecret upserts the encrypted blob for (tenant_id, secret_id).
// RLS discipline: advisory lock on (tenantID, secretID) then set_config GUC,
// matching the pattern in postgres.go Put.
func (s *PostgresStore) PutAgentSecret(ctx context.Context, rec AgentSecretRecord) error {
	if rec.TenantID == "" || rec.SecretID == "" {
		return fmt.Errorf("vault postgres: PutAgentSecret: tenant_id and secret_id are required")
	}

	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("vault postgres: PutAgentSecret: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// Serialise concurrent puts for the same (tenant_id, secret_id).
	if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(hashtextextended($1 || $2, 0))", rec.TenantID, rec.SecretID); err != nil {
		return fmt.Errorf("vault postgres: PutAgentSecret: advisory lock: %w", err)
	}

	// Pin RLS tenant for this transaction.
	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", rec.TenantID); err != nil {
		return fmt.Errorf("vault postgres: PutAgentSecret: set tenant: %w", err)
	}

	now := time.Now().UTC()

	_, err = tx.Exec(ctx,
		`INSERT INTO vault.agent_secrets
		        (secret_id, tenant_id, key_version, wrapped_dek, enc_payload, created_at, updated_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $6)
		 ON CONFLICT (secret_id) DO UPDATE
		    SET key_version = EXCLUDED.key_version,
		        wrapped_dek = EXCLUDED.wrapped_dek,
		        enc_payload = EXCLUDED.enc_payload,
		        updated_at  = EXCLUDED.updated_at`,
		rec.SecretID, rec.TenantID, rec.KeyVersion, rec.WrappedDEK, rec.EncPayload, now,
	)
	if err != nil {
		return fmt.Errorf("vault postgres: PutAgentSecret: upsert: %w", err)
	}

	if err = tx.Commit(ctx); err != nil {
		return fmt.Errorf("vault postgres: PutAgentSecret: commit: %w", err)
	}
	return nil
}

// GetAgentSecret returns the full row for (tenant_id, secret_id) or a wrapped
// sql.ErrNoRows-style error when absent.
func (s *PostgresStore) GetAgentSecret(ctx context.Context, tenantID, secretID string) (*AgentSecretRecord, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("vault postgres: GetAgentSecret: acquire conn: %w", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, fmt.Errorf("vault postgres: GetAgentSecret: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return nil, fmt.Errorf("vault postgres: GetAgentSecret: set tenant: %w", err)
	}

	var r AgentSecretRecord
	err = tx.QueryRow(ctx,
		`SELECT secret_id, tenant_id, key_version, wrapped_dek, enc_payload, created_at, updated_at
		   FROM vault.agent_secrets
		  WHERE tenant_id = $1 AND secret_id = $2
		  LIMIT 1`,
		tenantID, secretID,
	).Scan(&r.SecretID, &r.TenantID, &r.KeyVersion, &r.WrappedDEK, &r.EncPayload, &r.CreatedAt, &r.UpdatedAt)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, fmt.Errorf("vault postgres: GetAgentSecret: %w", ErrAgentSecretNotFound)
		}
		return nil, fmt.Errorf("vault postgres: GetAgentSecret: scan: %w", err)
	}

	_ = tx.Commit(ctx) // read-only
	return &r, nil
}

// DeleteAgentSecret removes the row for (tenant_id, secret_id). Idempotent.
func (s *PostgresStore) DeleteAgentSecret(ctx context.Context, tenantID, secretID string) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("vault postgres: DeleteAgentSecret: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return fmt.Errorf("vault postgres: DeleteAgentSecret: set tenant: %w", err)
	}

	_, err = tx.Exec(ctx,
		`DELETE FROM vault.agent_secrets WHERE tenant_id = $1 AND secret_id = $2`,
		tenantID, secretID,
	)
	if err != nil {
		return fmt.Errorf("vault postgres: DeleteAgentSecret: delete: %w", err)
	}

	if err = tx.Commit(ctx); err != nil {
		return fmt.Errorf("vault postgres: DeleteAgentSecret: commit: %w", err)
	}
	return nil
}

// ErrAgentSecretNotFound is returned by GetAgentSecret when no row exists.
var ErrAgentSecretNotFound = fmt.Errorf("agent secret not found")
