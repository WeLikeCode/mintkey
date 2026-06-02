// Package store — Postgres-backed credential store for the Vault Adapter.
//
// PostgresStore implements the same method set as Store (SQLite) so that the
// two backends are drop-in interchangeable at the factory level (C3).
//
// Tenant isolation is enforced by Postgres RLS via the GUC
// `app.current_tenant`.  Every query path sets this GUC before touching any
// row so that the RLS policy `tenant_isolation` on vault.credentials fires
// correctly.  The discipline is:
//
//   - Multi-statement operations (Put, Revoke): use a real transaction;
//     set_config('app.current_tenant', $1, true) scopes RLS to the transaction.
//   - Single-statement read operations (Get, ListVersions): acquire one
//     connection explicitly and wrap in a read-only transaction so that
//     set_config(..., true) (the third arg means transaction-local) is
//     correctly scoped.  Holding the conn ensures the SET is paired with the read.
//
// Note: SET LOCAL does not accept prepared-statement parameter placeholders in
// Postgres 16; use SELECT set_config('app.current_tenant', $1, true) instead.
//
// Source: design §8; ADR-0003; T-1.3.2.
package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgresStore wraps a pgxpool connection pool.
// Consumers that need a backend-agnostic handle should declare a local
// interface covering Put/Get/Revoke/ListVersions/Close; both Store and
// PostgresStore satisfy it.
type PostgresStore struct {
	pool *pgxpool.Pool
}

// NewPostgres opens a pgxpool connection pool and pings Postgres to confirm
// connectivity.  dsn must be a valid libpq connection string or URL.
func NewPostgres(ctx context.Context, dsn string) (*PostgresStore, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("vault postgres: parse dsn: %w", err)
	}

	// Low-throughput service; don't hammer the database.
	cfg.MaxConns = 10
	cfg.MinConns = 1

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("vault postgres: create pool: %w", err)
	}

	if err = pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("vault postgres: ping: %w", err)
	}

	return &PostgresStore{pool: pool}, nil
}

// Close releases all pooled connections.
func (s *PostgresStore) Close() error {
	s.pool.Close()
	return nil
}

// Put inserts a new credential version atomically:
//  1. set_config('app.current_tenant', ..., true) scopes RLS to rec.TenantID.
//  2. Compute next key_version = MAX(key_version)+1 per (tenant, service).
//  3. Demote any existing current row to is_current=false.
//  4. Insert new row as is_current=true, is_revoked=false.
//
// Returns the assigned key_version.
func (s *PostgresStore) Put(ctx context.Context, rec CredentialRecord) (uint32, error) {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return 0, fmt.Errorf("vault postgres: Put: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// Serialise concurrent Puts for the same (tenant_id, service_id) so that the
	// MAX(key_version)+1 computation cannot race and produce duplicate versions
	// that violate the UNIQUE(tenant_id, service_id, key_version) constraint.
	// The lock is automatically released at transaction commit or rollback.
	if _, err = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(hashtextextended($1 || $2, 0))", rec.TenantID, rec.ServiceID); err != nil {
		return 0, fmt.Errorf("vault postgres: Put: advisory lock: %w", err)
	}

	// Pin RLS tenant for this transaction.
	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", rec.TenantID); err != nil {
		return 0, fmt.Errorf("vault postgres: Put: set tenant: %w", err)
	}

	// Determine next version.
	var nextVer uint32
	if err = tx.QueryRow(ctx,
		`SELECT COALESCE(MAX(key_version), 0) + 1
		   FROM vault.credentials
		  WHERE tenant_id = $1 AND service_id = $2`,
		rec.TenantID, rec.ServiceID,
	).Scan(&nextVer); err != nil {
		return 0, fmt.Errorf("vault postgres: Put: max version: %w", err)
	}

	// Demote previous current row.
	if _, err = tx.Exec(ctx,
		`UPDATE vault.credentials
		    SET is_current = false
		  WHERE tenant_id = $1 AND service_id = $2 AND is_current = true`,
		rec.TenantID, rec.ServiceID,
	); err != nil {
		return 0, fmt.Errorf("vault postgres: Put: demote current: %w", err)
	}

	createdAt := rec.CreatedAt
	if createdAt == 0 {
		createdAt = time.Now().UnixNano()
	}

	if _, err = tx.Exec(ctx,
		`INSERT INTO vault.credentials
		        (credential_id, tenant_id, service_id, key_version, auth_scheme,
		         wrapped_dek, enc_payload, is_current, is_revoked, created_at,
		         target_url, header_name, query_param, target_address, ssh_user)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, true, false, $8, $9, $10, $11, $12, $13)`,
		rec.CredentialID, rec.TenantID, rec.ServiceID, nextVer, rec.AuthScheme,
		rec.WrappedDEK, rec.EncPayload, createdAt,
		rec.TargetURL, rec.HeaderName, rec.QueryParam, rec.TargetAddress, rec.SSHUser,
	); err != nil {
		return 0, fmt.Errorf("vault postgres: Put: insert: %w", err)
	}

	if err = tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("vault postgres: Put: commit: %w", err)
	}

	return nextVer, nil
}

// Get returns the credential record. Returns (nil, wrapped sql.ErrNoRows) when
// no row matches, identical to the SQLite backend.
//
// keyVersion == 0 means "the current version" (is_current=true).
//
// Connection discipline: we acquire a single pool connection and wrap the
// operation in a read-only transaction so set_config(..., true) (third arg =
// transaction-local) is correctly scoped before the SELECT.
func (s *PostgresStore) Get(ctx context.Context, tenantID, serviceID string, keyVersion uint32) (*CredentialRecord, error) {
	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("vault postgres: Get: acquire conn: %w", err)
	}
	defer conn.Release()

	// Wrap in an explicit transaction so SET LOCAL is scoped to this conn's
	// current transaction (required by Postgres — SET LOCAL outside any txn
	// raises an error in strict mode, and without a txn the GUC reverts after
	// the statement anyway).
	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, fmt.Errorf("vault postgres: Get: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return nil, fmt.Errorf("vault postgres: Get: set tenant: %w", err)
	}

	// LEFT JOIN public.services so that services.base_url (the canonical SSH dial
	// target per ADR-0023 Phase 3) is returned alongside the credential row.
	// LEFT JOIN public.email_services so that email_services.tls_insecure_skip_verify
	// (ADR-0024) is returned for email service credentials.
	// COALESCE(s.base_url, '') ensures a NULL base_url scans cleanly into a string.
	// COALESCE(es.tls_insecure_skip_verify, false) ensures a NULL (non-email service)
	// scans cleanly to false.
	// The JOINs are tenant-scoped via the WHERE clause; RLS on vault.credentials is
	// already enforced by the set_config GUC above.
	const cols = `vc.credential_id, vc.tenant_id, vc.service_id, vc.key_version, vc.auth_scheme,
	              vc.wrapped_dek, vc.enc_payload, vc.is_current, vc.is_revoked, vc.created_at,
	              vc.target_url, vc.header_name, vc.query_param, vc.target_address, vc.ssh_user,
	              COALESCE(s.base_url, '') AS service_base_url,
	              COALESCE(es.tls_insecure_skip_verify, false) AS tls_insecure_skip_verify`

	var row pgx.Row
	if keyVersion == 0 {
		// Match sqlite: filter only on is_current=true (not is_revoked) —
		// is_current=true already implies is_revoked=false by the Put/Revoke invariant.
		row = tx.QueryRow(ctx,
			`SELECT `+cols+`
			   FROM vault.credentials vc
			   LEFT JOIN public.services s ON s.id = vc.service_id
			   LEFT JOIN public.email_services es ON es.id = vc.service_id AND es.deleted_at IS NULL
			  WHERE vc.tenant_id = $1 AND vc.service_id = $2
			    AND vc.is_current = true
			  LIMIT 1`,
			tenantID, serviceID,
		)
	} else {
		// Match sqlite.go: Get(keyVersion!=0) returns the row regardless of
		// is_revoked so callers can inspect the revoked flag.  The is_revoked
		// filter must NOT be applied here — sqlite never does it on the explicit-
		// version branch, and the round-2 divergence caused sqlite to return
		// (row{is_revoked=true}, nil) while postgres returned (nil, sql.ErrNoRows).
		row = tx.QueryRow(ctx,
			`SELECT `+cols+`
			   FROM vault.credentials vc
			   LEFT JOIN public.services s ON s.id = vc.service_id
			   LEFT JOIN public.email_services es ON es.id = vc.service_id AND es.deleted_at IS NULL
			  WHERE vc.tenant_id = $1 AND vc.service_id = $2
			    AND vc.key_version = $3
			  LIMIT 1`,
			tenantID, serviceID, keyVersion,
		)
	}

	rec, err := scanPgRecord(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			// Surface both nil-nil (not-found idiom) AND wrapped sql.ErrNoRows
			// so that callers using errors.Is(err, sql.ErrNoRows) also work.
			return nil, fmt.Errorf("vault postgres: Get: %w", sql.ErrNoRows)
		}
		return nil, fmt.Errorf("vault postgres: Get: %w", err)
	}

	_ = tx.Commit(ctx) // read-only; ignore commit error
	return rec, nil
}

// Revoke soft-deletes a non-current credential version (is_revoked=true).
// Returns ErrRevokeCurrent when the target is the active version.
// Returns a wrapped sql.ErrNoRows when keyVersion does not exist.
//
// keyVersion must be > 0 for Revoke (revoking "current" is always rejected).
func (s *PostgresStore) Revoke(ctx context.Context, tenantID, serviceID string, keyVersion uint32) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("vault postgres: Revoke: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return fmt.Errorf("vault postgres: Revoke: set tenant: %w", err)
	}

	var isCurrent bool
	if err = tx.QueryRow(ctx,
		`SELECT is_current FROM vault.credentials
		  WHERE tenant_id = $1 AND service_id = $2 AND key_version = $3`,
		tenantID, serviceID, keyVersion,
	).Scan(&isCurrent); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return fmt.Errorf("vault postgres: Revoke: version %d not found: %w", keyVersion, sql.ErrNoRows)
		}
		return fmt.Errorf("vault postgres: Revoke: lookup: %w", err)
	}

	if isCurrent {
		return ErrRevokeCurrent
	}

	if _, err = tx.Exec(ctx,
		`UPDATE vault.credentials
		    SET is_revoked = true
		  WHERE tenant_id = $1 AND service_id = $2 AND key_version = $3`,
		tenantID, serviceID, keyVersion,
	); err != nil {
		return fmt.Errorf("vault postgres: Revoke: update: %w", err)
	}

	if err = tx.Commit(ctx); err != nil {
		return fmt.Errorf("vault postgres: Revoke: commit: %w", err)
	}
	return nil
}

// ListVersions returns metadata-only records (WrappedDEK and EncPayload are
// empty) for all versions of (tenantID, serviceID).
//
// afterKeyVersion is an exclusive lower bound (pass 0 for "all").
// limit caps the result set; values of 0 or >200 are clamped to 50.
//
// Connection discipline: same as Get — acquire one conn, SET LOCAL, query.
func (s *PostgresStore) ListVersions(ctx context.Context, tenantID, serviceID string, afterKeyVersion, limit uint32) ([]CredentialRecord, error) {
	if limit == 0 || limit > 200 {
		limit = 50
	}

	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("vault postgres: ListVersions: acquire conn: %w", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, fmt.Errorf("vault postgres: ListVersions: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		return nil, fmt.Errorf("vault postgres: ListVersions: set tenant: %w", err)
	}

	rows, err := tx.Query(ctx,
		`SELECT credential_id, tenant_id, service_id, key_version, auth_scheme,
		        is_current, is_revoked, created_at
		   FROM vault.credentials
		  WHERE tenant_id = $1 AND service_id = $2 AND key_version > $3
		  ORDER BY key_version ASC
		  LIMIT $4`,
		tenantID, serviceID, afterKeyVersion, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("vault postgres: ListVersions: query: %w", err)
	}
	defer rows.Close()

	var result []CredentialRecord
	for rows.Next() {
		var r CredentialRecord
		if err = rows.Scan(
			&r.CredentialID, &r.TenantID, &r.ServiceID,
			&r.KeyVersion, &r.AuthScheme,
			&r.IsCurrent, &r.IsRevoked, &r.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("vault postgres: ListVersions: scan: %w", err)
		}
		// WrappedDEK and EncPayload intentionally left nil/empty (metadata only).
		result = append(result, r)
	}

	if err = rows.Err(); err != nil {
		return nil, fmt.Errorf("vault postgres: ListVersions: rows: %w", err)
	}

	_ = tx.Commit(ctx) // read-only
	return result, nil
}

// scanPgRecord scans a pgx.Row into a CredentialRecord (full columns).
// The query must SELECT the 17-column set produced by the Get() LEFT JOIN:
//
//	vc.credential_id, vc.tenant_id, vc.service_id, vc.key_version, vc.auth_scheme,
//	vc.wrapped_dek, vc.enc_payload, vc.is_current, vc.is_revoked, vc.created_at,
//	vc.target_url, vc.header_name, vc.query_param, vc.target_address, vc.ssh_user,
//	COALESCE(s.base_url, '') AS service_base_url,
//	COALESCE(es.tls_insecure_skip_verify, false) AS tls_insecure_skip_verify
func scanPgRecord(row pgx.Row) (*CredentialRecord, error) {
	var r CredentialRecord
	if err := row.Scan(
		&r.CredentialID, &r.TenantID, &r.ServiceID,
		&r.KeyVersion, &r.AuthScheme,
		&r.WrappedDEK, &r.EncPayload,
		&r.IsCurrent, &r.IsRevoked, &r.CreatedAt,
		&r.TargetURL, &r.HeaderName, &r.QueryParam,
		&r.TargetAddress, &r.SSHUser,
		&r.ServiceBaseUrl,
		&r.TlsInsecureSkipVerify,
	); err != nil {
		return nil, err
	}
	return &r, nil
}
