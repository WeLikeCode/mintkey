// Package store provides a SQLite-backed credential store for the Vault Adapter.
//
// Credentials are stored as envelope-encrypted BLOBs: the wrapped DEK and the
// encrypted payload are kept in separate columns so that KEK rotation can
// re-wrap the DEK without touching the data blob (ADR-0003).
//
// Source: design §8; ADR-0003; T-1.3.1.
package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	_ "modernc.org/sqlite" // pure-Go SQLite driver (ADR-0011); registers driver name "sqlite", no cgo
)

// ErrRevokeCurrent is returned when a caller attempts to revoke the current
// (active) version of a credential.
var ErrRevokeCurrent = errors.New("store: cannot revoke the current credential version")

// CredentialRecord holds one credential version as stored in SQLite.
// WrappedDEK and EncPayload are omitted (empty) in ListVersions results.
type CredentialRecord struct {
	CredentialID  string
	TenantID      string
	ServiceID     string
	KeyVersion    uint32
	AuthScheme    int32
	WrappedDEK    []byte
	EncPayload    []byte
	IsCurrent     bool
	IsRevoked     bool
	CreatedAt     int64 // Unix nanoseconds
	TargetURL     string
	HeaderName    string // injection hint: HTTP header name (e.g. "X-API-Key") — UX-C6
	QueryParam    string // injection hint: query parameter name (e.g. "api_key") — UX-C6
	TargetAddress string // SSH-only: "host:port" of the backend SSH server — ADR-0021
	SSHUser       string // SSH-only: SSH username to authenticate as — ADR-0021

	// ServiceBaseUrl is the canonical upstream address from public.services.base_url
	// (e.g. "ssh://host:22"). Populated only by PostgresStore.Get via a LEFT JOIN on
	// public.services. SQLite store leaves this empty. ADR-0023 / Phase 3.
	ServiceBaseUrl string

	// TlsInsecureSkipVerify disables TLS certificate verification for email-proxy
	// IMAP/SMTP connections when true. Populated only by PostgresStore.Get via a
	// LEFT JOIN on public.email_services. SQLite store leaves this false.
	// ADR-0024.
	TlsInsecureSkipVerify bool
}

// Store wraps an SQLite database connection.
type Store struct {
	db *sql.DB
}

const schema = `
CREATE TABLE IF NOT EXISTS credentials (
    credential_id  TEXT    PRIMARY KEY,
    tenant_id      TEXT    NOT NULL,
    service_id     TEXT    NOT NULL,
    key_version    INTEGER NOT NULL,
    auth_scheme    INTEGER NOT NULL DEFAULT 0,
    wrapped_dek    BLOB    NOT NULL,
    enc_payload    BLOB    NOT NULL,
    is_current     INTEGER NOT NULL DEFAULT 1,
    is_revoked     INTEGER NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL,
    target_url     TEXT    NOT NULL DEFAULT '',
    header_name    TEXT    NOT NULL DEFAULT '',
    query_param    TEXT    NOT NULL DEFAULT '',
    target_address TEXT    NOT NULL DEFAULT '',
    ssh_user       TEXT    NOT NULL DEFAULT '',
    UNIQUE(tenant_id, service_id, key_version)
);
CREATE INDEX IF NOT EXISTS idx_credentials_tenant_service
    ON credentials(tenant_id, service_id);
`

// New opens (or creates) the SQLite database at path and applies the schema.
func New(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("store: open %s: %w", path, err)
	}

	// Single writer to avoid SQLITE_BUSY on concurrent calls.
	db.SetMaxOpenConns(1)

	if _, err = db.Exec(schema); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("store: migrate: %w", err)
	}

	// Add optional columns to pre-existing databases that lack them.
	if err = migrateAddColumns(db); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("store: migrate columns: %w", err)
	}

	return &Store{db: db}, nil
}

// migrateAddColumns adds optional columns when they are absent (one-time migrations
// for databases created before these fields were introduced).
func migrateAddColumns(db *sql.DB) error {
	rows, err := db.Query(`PRAGMA table_info(credentials)`)
	if err != nil {
		return fmt.Errorf("pragma table_info: %w", err)
	}
	defer rows.Close()

	existing := make(map[string]bool)
	for rows.Next() {
		var cid int
		var name, colType string
		var notNull, pk int
		var dfltValue sql.NullString
		if err = rows.Scan(&cid, &name, &colType, &notNull, &dfltValue, &pk); err != nil {
			return fmt.Errorf("scan pragma row: %w", err)
		}
		existing[name] = true
	}
	if err = rows.Err(); err != nil {
		return err
	}

	migrations := []struct {
		col string
		ddl string
	}{
		{"target_url", `ALTER TABLE credentials ADD COLUMN target_url TEXT NOT NULL DEFAULT ''`},
		{"header_name", `ALTER TABLE credentials ADD COLUMN header_name TEXT NOT NULL DEFAULT ''`},
		{"query_param", `ALTER TABLE credentials ADD COLUMN query_param TEXT NOT NULL DEFAULT ''`},
		{"target_address", `ALTER TABLE credentials ADD COLUMN target_address TEXT NOT NULL DEFAULT ''`},
		{"ssh_user", `ALTER TABLE credentials ADD COLUMN ssh_user TEXT NOT NULL DEFAULT ''`},
	}
	for _, m := range migrations {
		if existing[m.col] {
			continue
		}
		if _, err = db.Exec(m.ddl); err != nil {
			return fmt.Errorf("add column %s: %w", m.col, err)
		}
	}
	return nil
}

// Close releases the underlying database connection.
func (s *Store) Close() error { return s.db.Close() }

// Put inserts a new credential version.
//
// It atomically:
//  1. Determines the next key_version (MAX(key_version)+1 per tenant+service, min 1).
//  2. Marks all previous versions as non-current.
//  3. Inserts the new row as is_current=1.
//
// Returns the assigned key_version.
func (s *Store) Put(ctx context.Context, rec CredentialRecord) (uint32, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, fmt.Errorf("store.Put: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	// Determine next version number.
	var maxVer sql.NullInt64
	if err = tx.QueryRowContext(ctx,
		`SELECT MAX(key_version) FROM credentials WHERE tenant_id=? AND service_id=?`,
		rec.TenantID, rec.ServiceID,
	).Scan(&maxVer); err != nil {
		return 0, fmt.Errorf("store.Put: max version: %w", err)
	}

	var nextVer uint32 = 1
	if maxVer.Valid {
		nextVer = uint32(maxVer.Int64) + 1
	}

	// Mark previous versions non-current.
	if _, err = tx.ExecContext(ctx,
		`UPDATE credentials SET is_current=0 WHERE tenant_id=? AND service_id=?`,
		rec.TenantID, rec.ServiceID,
	); err != nil {
		return 0, fmt.Errorf("store.Put: demote current: %w", err)
	}

	createdAt := rec.CreatedAt
	if createdAt == 0 {
		createdAt = time.Now().UnixNano()
	}

	if _, err = tx.ExecContext(ctx,
		`INSERT INTO credentials
             (credential_id, tenant_id, service_id, key_version, auth_scheme,
              wrapped_dek, enc_payload, is_current, is_revoked, created_at, target_url,
              header_name, query_param, target_address, ssh_user)
         VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?)`,
		rec.CredentialID, rec.TenantID, rec.ServiceID, nextVer, rec.AuthScheme,
		rec.WrappedDEK, rec.EncPayload, createdAt, rec.TargetURL,
		rec.HeaderName, rec.QueryParam, rec.TargetAddress, rec.SSHUser,
	); err != nil {
		return 0, fmt.Errorf("store.Put: insert: %w", err)
	}

	if err = tx.Commit(); err != nil {
		return 0, fmt.Errorf("store.Put: commit: %w", err)
	}

	return nextVer, nil
}

// Get retrieves a credential record.
// Pass keyVersion=0 to retrieve the current version.
// Returns sql.ErrNoRows (wrapped) when no matching row is found.
func (s *Store) Get(ctx context.Context, tenantID, serviceID string, keyVersion uint32) (*CredentialRecord, error) {
	var row *sql.Row
	if keyVersion == 0 {
		row = s.db.QueryRowContext(ctx,
			`SELECT credential_id, tenant_id, service_id, key_version, auth_scheme,
                    wrapped_dek, enc_payload, is_current, is_revoked, created_at, target_url,
                    header_name, query_param, target_address, ssh_user
             FROM credentials
             WHERE tenant_id=? AND service_id=? AND is_current=1`,
			tenantID, serviceID,
		)
	} else {
		row = s.db.QueryRowContext(ctx,
			`SELECT credential_id, tenant_id, service_id, key_version, auth_scheme,
                    wrapped_dek, enc_payload, is_current, is_revoked, created_at, target_url,
                    header_name, query_param, target_address, ssh_user
             FROM credentials
             WHERE tenant_id=? AND service_id=? AND key_version=?`,
			tenantID, serviceID, keyVersion,
		)
	}

	rec, err := scanRecord(row)
	if err != nil {
		return nil, fmt.Errorf("store.Get: %w", err)
	}
	return rec, nil
}

// Revoke soft-deletes a non-current credential version by setting is_revoked=1.
// Returns ErrRevokeCurrent if the target version is currently active.
// Returns a wrapped sql.ErrNoRows if the version does not exist.
func (s *Store) Revoke(ctx context.Context, tenantID, serviceID string, keyVersion uint32) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("store.Revoke: begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	var isCurrent int
	if err = tx.QueryRowContext(ctx,
		`SELECT is_current FROM credentials WHERE tenant_id=? AND service_id=? AND key_version=?`,
		tenantID, serviceID, keyVersion,
	).Scan(&isCurrent); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return fmt.Errorf("store.Revoke: version %d not found: %w", keyVersion, sql.ErrNoRows)
		}
		return fmt.Errorf("store.Revoke: lookup: %w", err)
	}

	if isCurrent == 1 {
		return ErrRevokeCurrent
	}

	if _, err = tx.ExecContext(ctx,
		`UPDATE credentials SET is_revoked=1 WHERE tenant_id=? AND service_id=? AND key_version=?`,
		tenantID, serviceID, keyVersion,
	); err != nil {
		return fmt.Errorf("store.Revoke: update: %w", err)
	}

	return tx.Commit()
}

// ListVersions returns metadata-only records (WrappedDEK and EncPayload are
// empty) for all versions of (tenantID, serviceID).
//
// afterKeyVersion is an exclusive lower bound (pass 0 for "all").
// limit caps the result set; values of 0 or >200 are clamped to 50.
func (s *Store) ListVersions(ctx context.Context, tenantID, serviceID string, afterKeyVersion, limit uint32) ([]CredentialRecord, error) {
	if limit == 0 || limit > 200 {
		limit = 50
	}

	rows, err := s.db.QueryContext(ctx,
		`SELECT credential_id, tenant_id, service_id, key_version, auth_scheme,
                is_current, is_revoked, created_at
         FROM credentials
         WHERE tenant_id=? AND service_id=? AND key_version > ?
         ORDER BY key_version ASC
         LIMIT ?`,
		tenantID, serviceID, afterKeyVersion, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("store.ListVersions: query: %w", err)
	}
	defer rows.Close()

	var result []CredentialRecord
	for rows.Next() {
		var r CredentialRecord
		var isCurrent, isRevoked int
		if err = rows.Scan(
			&r.CredentialID, &r.TenantID, &r.ServiceID,
			&r.KeyVersion, &r.AuthScheme,
			&isCurrent, &isRevoked, &r.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("store.ListVersions: scan: %w", err)
		}
		r.IsCurrent = isCurrent == 1
		r.IsRevoked = isRevoked == 1
		// WrappedDEK and EncPayload intentionally left nil/empty.
		result = append(result, r)
	}

	return result, rows.Err()
}

// scanRecord scans one sql.Row into a CredentialRecord (full columns).
func scanRecord(row *sql.Row) (*CredentialRecord, error) {
	var r CredentialRecord
	var isCurrent, isRevoked int
	if err := row.Scan(
		&r.CredentialID, &r.TenantID, &r.ServiceID,
		&r.KeyVersion, &r.AuthScheme,
		&r.WrappedDEK, &r.EncPayload,
		&isCurrent, &isRevoked, &r.CreatedAt, &r.TargetURL,
		&r.HeaderName, &r.QueryParam, &r.TargetAddress, &r.SSHUser,
	); err != nil {
		return nil, err
	}
	r.IsCurrent = isCurrent == 1
	r.IsRevoked = isRevoked == 1
	return &r, nil
}
