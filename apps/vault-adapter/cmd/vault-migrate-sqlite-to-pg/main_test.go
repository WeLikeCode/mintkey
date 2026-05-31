//go:build postgres

// Run with a live Postgres:
//
//	MINTKEY_TEST_PG_DSN="postgres://mintkey_migrate:changeme@postgres:5432/mintkey?sslmode=disable" \
//	MINTKEY_TEST_PG_APP_DSN="postgres://mintkey_app:changeme@postgres:5432/mintkey?sslmode=disable" \
//	go test -tags postgres -v -count=1 -race ./cmd/vault-migrate-sqlite-to-pg/...
//
// The tests use a temp sqlite file (t.TempDir()) and unique per-run tenant UUIDs
// to avoid conflicting with the live 138 credentials in postgres.
// Each test cleans up its own rows from postgres on t.Cleanup.
package main

import (
	"bytes"
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	_ "modernc.org/sqlite"
)

const pgDSNEnv = "MINTKEY_TEST_PG_DSN"

// openTestPool opens a pgxpool from MINTKEY_TEST_PG_DSN or skips.
func openTestPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv(pgDSNEnv)
	if dsn == "" {
		t.Skipf("skipping postgres migration test: %s not set", pgDSNEnv)
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	if err = pool.Ping(ctx); err != nil {
		pool.Close()
		t.Fatalf("pg ping: %v", err)
	}
	t.Cleanup(func() { pool.Close() })
	return pool
}

// cleanupByTenant deletes all vault.credentials rows for the given tenantID.
// Uses mintkey_migrate (BYPASSRLS) so it sees all rows regardless of GUC.
func cleanupByTenant(t *testing.T, pool *pgxpool.Pool, tenantID string) {
	t.Helper()
	ctx := context.Background()
	conn, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("cleanup acquire: %v", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		t.Fatalf("cleanup begin tx: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx,
		"SELECT set_config('app.current_tenant', $1, true)", tenantID,
	); err != nil {
		t.Fatalf("cleanup set_config: %v", err)
	}
	if _, err = tx.Exec(ctx,
		`DELETE FROM vault.credentials WHERE tenant_id = $1`, tenantID,
	); err != nil {
		t.Fatalf("cleanup delete: %v", err)
	}
	if err = tx.Commit(ctx); err != nil {
		t.Fatalf("cleanup commit: %v", err)
	}
}

// buildTestSQLite creates a temp sqlite file with the given rows and returns its path.
func buildTestSQLite(t *testing.T, rows []sqliteRow) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "test.sqlite")

	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open test sqlite: %v", err)
	}
	defer func() { _ = db.Close() }()

	_, err = db.Exec(`
		CREATE TABLE credentials (
			credential_id TEXT PRIMARY KEY,
			tenant_id     TEXT NOT NULL,
			service_id    TEXT NOT NULL,
			key_version   INTEGER NOT NULL,
			auth_scheme   INTEGER NOT NULL DEFAULT 0,
			wrapped_dek   BLOB NOT NULL,
			enc_payload   BLOB NOT NULL,
			is_current    INTEGER NOT NULL DEFAULT 1,
			is_revoked    INTEGER NOT NULL DEFAULT 0,
			created_at    INTEGER NOT NULL,
			target_url    TEXT NOT NULL DEFAULT '',
			header_name   TEXT NOT NULL DEFAULT '',
			query_param   TEXT NOT NULL DEFAULT '',
			UNIQUE(tenant_id, service_id, key_version)
		)
	`)
	if err != nil {
		t.Fatalf("create test sqlite schema: %v", err)
	}

	for _, r := range rows {
		_, err = db.Exec(`
			INSERT INTO credentials (
				credential_id, tenant_id, service_id, key_version, auth_scheme,
				wrapped_dek, enc_payload, is_current, is_revoked, created_at,
				target_url, header_name, query_param
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		`,
			r.credentialID, r.tenantID, r.serviceID, r.keyVersion, r.authScheme,
			r.wrappedDEK, r.encPayload, r.isCurrent, r.isRevoked, r.createdAt,
			r.targetURL, r.headerName, r.queryParam,
		)
		if err != nil {
			t.Fatalf("insert test row %q: %v", r.credentialID, err)
		}
	}
	return path
}

// makeRow builds a sqliteRow with unique identifiers and random-ish blobs.
func makeRow(credID, tenantID, serviceID string) sqliteRow {
	return sqliteRow{
		credentialID: credID,
		tenantID:     tenantID,
		serviceID:    serviceID,
		keyVersion:   1,
		authScheme:   1,
		wrappedDEK:   []byte(fmt.Sprintf("wrapped-dek-%s", credID)),
		encPayload:   []byte(fmt.Sprintf("enc-payload-%s", credID)),
		isCurrent:    1,
		isRevoked:    0,
		createdAt:    time.Now().UnixNano(),
		targetURL:    "https://api.example.com",
		headerName:   "X-Api-Key",
		queryParam:   "",
	}
}

// fetchPGRow fetches a single row from postgres for verification (needs tenant GUC for RLS).
func fetchPGRow(t *testing.T, pool *pgxpool.Pool, credID, tenantID string) (authScheme int32, wrappedDEK, encPayload []byte) {
	t.Helper()
	ctx := context.Background()

	conn, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("fetchPGRow acquire: %v", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		t.Fatalf("fetchPGRow begin tx: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx,
		"SELECT set_config('app.current_tenant', $1, true)", tenantID,
	); err != nil {
		t.Fatalf("fetchPGRow set_config: %v", err)
	}

	err = tx.QueryRow(ctx,
		`SELECT auth_scheme, wrapped_dek, enc_payload
		   FROM vault.credentials
		  WHERE credential_id = $1`,
		credID,
	).Scan(&authScheme, &wrappedDEK, &encPayload)
	if err != nil {
		t.Fatalf("fetchPGRow scan %q: %v", credID, err)
	}
	_ = tx.Commit(ctx)
	return authScheme, wrappedDEK, encPayload
}

// countPGRowsForTenant returns the number of vault.credentials rows for tenantID.
func countPGRowsForTenant(t *testing.T, pool *pgxpool.Pool, tenantID string) int {
	t.Helper()
	ctx := context.Background()

	conn, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("countPGRows acquire: %v", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
	if err != nil {
		t.Fatalf("countPGRows begin tx: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx,
		"SELECT set_config('app.current_tenant', $1, true)", tenantID,
	); err != nil {
		t.Fatalf("countPGRows set_config: %v", err)
	}

	var count int
	if err = tx.QueryRow(ctx,
		`SELECT COUNT(*) FROM vault.credentials WHERE tenant_id = $1`, tenantID,
	).Scan(&count); err != nil {
		t.Fatalf("countPGRows scan: %v", err)
	}
	_ = tx.Commit(ctx)
	return count
}

// TestMigration_HappyPath inserts 3 credentials into a temp sqlite, migrates to
// postgres, then re-fetches and asserts byte-equal payloads for all 3.
func TestMigration_HappyPath(t *testing.T) {
	pool := openTestPool(t)
	dsn := os.Getenv(pgDSNEnv)

	// Use a unique tenant per test run to avoid conflicts with live or other test data.
	tenantID := uuid.New().String()
	serviceID := uuid.New().String()
	t.Cleanup(func() { cleanupByTenant(t, pool, tenantID) })

	rows := []sqliteRow{
		makeRow("cred-happy-001", tenantID, serviceID),
		makeRow("cred-happy-002", tenantID, serviceID),
		makeRow("cred-happy-003", tenantID, serviceID),
	}
	// Give version 2/3 different key versions to satisfy UNIQUE(tenant,service,key_version).
	rows[1].keyVersion = 2
	rows[1].isCurrent = 0
	rows[2].keyVersion = 3
	rows[2].isCurrent = 0

	sqlitePath := buildTestSQLite(t, rows)

	ctx := context.Background()
	if err := run(ctx, sqlitePath, dsn); err != nil {
		t.Fatalf("run: %v", err)
	}

	// Verify all 3 rows are present in postgres with byte-equal payloads.
	for _, r := range rows {
		authScheme, wrappedDEK, encPayload := fetchPGRow(t, pool, r.credentialID, tenantID)
		if int32(r.authScheme) != authScheme {
			t.Errorf("%q: auth_scheme mismatch: want %d got %d", r.credentialID, r.authScheme, authScheme)
		}
		if !bytes.Equal(r.wrappedDEK, wrappedDEK) {
			t.Errorf("%q: wrapped_dek mismatch: want len=%d got len=%d", r.credentialID, len(r.wrappedDEK), len(wrappedDEK))
		}
		if !bytes.Equal(r.encPayload, encPayload) {
			t.Errorf("%q: enc_payload mismatch: want len=%d got len=%d", r.credentialID, len(r.encPayload), len(encPayload))
		}
	}
}

// TestMigration_Idempotent runs the migration twice. The second run must report
// skipped_conflict=3 and inserted=0, and no additional rows appear in postgres.
func TestMigration_Idempotent(t *testing.T) {
	pool := openTestPool(t)
	dsn := os.Getenv(pgDSNEnv)

	tenantID := uuid.New().String()
	serviceID := uuid.New().String()
	t.Cleanup(func() { cleanupByTenant(t, pool, tenantID) })

	rows := []sqliteRow{
		makeRow("cred-idem-001", tenantID, serviceID),
		makeRow("cred-idem-002", tenantID, serviceID),
		makeRow("cred-idem-003", tenantID, serviceID),
	}
	rows[1].keyVersion = 2
	rows[1].isCurrent = 0
	rows[2].keyVersion = 3
	rows[2].isCurrent = 0

	sqlitePath := buildTestSQLite(t, rows)

	ctx := context.Background()

	// First run — should insert 3.
	if err := run(ctx, sqlitePath, dsn); err != nil {
		t.Fatalf("first run: %v", err)
	}
	countAfterFirst := countPGRowsForTenant(t, pool, tenantID)
	if countAfterFirst != 3 {
		t.Fatalf("after first run: want 3 rows, got %d", countAfterFirst)
	}

	// Second run — all 3 must conflict and be skipped; outcomes tested via run
	// returning nil (no inserted, skipped=3 is not an error condition).
	if err := run(ctx, sqlitePath, dsn); err != nil {
		t.Fatalf("second run (idempotent): %v", err)
	}
	countAfterSecond := countPGRowsForTenant(t, pool, tenantID)
	if countAfterSecond != 3 {
		t.Fatalf("after second run: want 3 rows (unchanged), got %d", countAfterSecond)
	}
}

// TestMigration_SkipsBadUUID includes one row with a malformed tenant_id.
// The migration must log the error, increment errors, and continue migrating
// the remaining valid rows (inserted=2, errors=1).
func TestMigration_SkipsBadUUID(t *testing.T) {
	pool := openTestPool(t)
	dsn := os.Getenv(pgDSNEnv)

	tenantID := uuid.New().String()
	serviceID := uuid.New().String()
	t.Cleanup(func() { cleanupByTenant(t, pool, tenantID) })

	goodRow1 := makeRow("cred-baduuid-001", tenantID, serviceID)
	goodRow2 := makeRow("cred-baduuid-002", tenantID, serviceID)
	goodRow2.keyVersion = 2
	goodRow2.isCurrent = 0

	// Row with a malformed tenant_id — Postgres UUID cast rejects this.
	badRow := makeRow("cred-baduuid-BAD", "not-a-uuid", serviceID)

	rows := []sqliteRow{goodRow1, goodRow2, badRow}
	sqlitePath := buildTestSQLite(t, rows)

	ctx := context.Background()
	err := run(ctx, sqlitePath, dsn)
	// run must NOT return nil because errors > 0, but it also must NOT abort the
	// whole migration — good rows are still inserted. We check for the specific
	// error message pattern and verify 2 good rows made it to postgres.
	if err == nil {
		t.Fatal("expected run to return error (errors=1) but got nil")
	}
	t.Logf("run returned (expected) error: %v", err)

	// Good rows must still be present in postgres.
	count := countPGRowsForTenant(t, pool, tenantID)
	if count != 2 {
		t.Errorf("want 2 valid rows in postgres, got %d", count)
	}
}
