// Command vault-migrate-sqlite-to-pg copies every credential row from a
// vault.sqlite file into the Postgres vault.credentials table.
//
// The migration is IDEMPOTENT: ON CONFLICT (credential_id) DO NOTHING means
// re-running against a partially-migrated state is safe.
//
// Usage:
//
//	MINTKEY_VAULT_SQLITE_PATH=/var/lib/mintkey/vault.sqlite \
//	MINTKEY_VAULT_PG_DSN="postgres://mintkey_migrate:...@postgres:5432/mintkey?sslmode=disable" \
//	go run ./cmd/vault-migrate-sqlite-to-pg/...
//
// Flags (override env vars):
//
//	--sqlite   path to vault.sqlite
//	--pg-dsn   postgres DSN
//
// Source: design §8; ADR-0003; T-1.3.4 (C4).
package main

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"net/url"
	"os"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	_ "modernc.org/sqlite" // pure-Go SQLite driver
)

// outcomes tracks migration counters.
type outcomes struct {
	read            int
	inserted        int
	skippedConflict int
	errors          int
}

// sqliteRow is a raw scan target from the sqlite credentials table (int columns
// for is_current/is_revoked as sqlite stores them as INTEGER 0/1).
type sqliteRow struct {
	credentialID string
	tenantID     string
	serviceID    string
	keyVersion   int64
	authScheme   int64
	wrappedDEK   []byte
	encPayload   []byte
	isCurrent    int64
	isRevoked    int64
	createdAt    int64
	targetURL    string
	headerName   string
	queryParam   string
}

func main() {
	sqlitePath := flag.String("sqlite", os.Getenv("MINTKEY_VAULT_SQLITE_PATH"), "path to vault.sqlite")
	pgDSN := flag.String("pg-dsn", os.Getenv("MINTKEY_VAULT_PG_DSN"), "postgres DSN")
	flag.Parse()

	if *sqlitePath == "" {
		log.Fatal("vault-migrate: MINTKEY_VAULT_SQLITE_PATH (or --sqlite) is required")
	}
	if *pgDSN == "" {
		log.Fatal("vault-migrate: MINTKEY_VAULT_PG_DSN (or --pg-dsn) is required")
	}

	ctx := context.Background()

	if err := run(ctx, *sqlitePath, *pgDSN); err != nil {
		log.Fatalf("vault-migrate: %v", err)
	}
}

func run(ctx context.Context, sqlitePath, pgDSN string) error {
	// ── Open SQLite read-only ──────────────────────────────────────────────────
	sqliteURL := "file:" + sqlitePath + "?mode=ro"
	sqliteDB, err := sql.Open("sqlite", sqliteURL)
	if err != nil {
		return fmt.Errorf("open sqlite %q: %w", sqlitePath, err)
	}
	defer func() { _ = sqliteDB.Close() }()
	sqliteDB.SetMaxOpenConns(1)

	if err = sqliteDB.PingContext(ctx); err != nil {
		return fmt.Errorf("ping sqlite: %w", err)
	}

	// ── Open Postgres ──────────────────────────────────────────────────────────
	cfg, err := pgxpool.ParseConfig(pgDSN)
	if err != nil {
		return fmt.Errorf("parse pg dsn: %w", err)
	}
	cfg.MaxConns = 5
	cfg.MinConns = 1

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return fmt.Errorf("create pg pool: %w", err)
	}
	defer pool.Close()

	if err = pool.Ping(ctx); err != nil {
		return fmt.Errorf("ping postgres: %w", err)
	}

	// ── Read all rows from sqlite ──────────────────────────────────────────────
	rows, err := sqliteDB.QueryContext(ctx, `
		SELECT credential_id, tenant_id, service_id, key_version, auth_scheme,
		       wrapped_dek, enc_payload, is_current, is_revoked, created_at,
		       target_url, header_name, query_param
		  FROM credentials
		 ORDER BY tenant_id, credential_id
	`)
	if err != nil {
		return fmt.Errorf("query sqlite credentials: %w", err)
	}
	defer rows.Close()

	var o outcomes
	// Collect sample IDs for post-insert verification (reservoir sample, k=5).
	var sampleIDs []string
	var allIDs []string

	for rows.Next() {
		var r sqliteRow
		if err = rows.Scan(
			&r.credentialID, &r.tenantID, &r.serviceID,
			&r.keyVersion, &r.authScheme,
			&r.wrappedDEK, &r.encPayload,
			&r.isCurrent, &r.isRevoked, &r.createdAt,
			&r.targetURL, &r.headerName, &r.queryParam,
		); err != nil {
			return fmt.Errorf("scan sqlite row: %w", err)
		}

		o.read++
		allIDs = append(allIDs, r.credentialID)

		inserted, insertErr := insertRow(ctx, pool, r)
		if insertErr != nil {
			log.Printf("vault-migrate: ERROR row %q (tenant=%s service=%s): %v",
				r.credentialID, r.tenantID, r.serviceID, insertErr)
			o.errors++
			continue
		}
		if inserted {
			o.inserted++
		} else {
			o.skippedConflict++
		}
	}
	if err = rows.Err(); err != nil {
		return fmt.Errorf("iterate sqlite rows: %w", err)
	}

	// ── Build 5-element reservoir sample ──────────────────────────────────────
	sampleIDs = reservoirSample(allIDs, 5)

	// ── Sample verification ────────────────────────────────────────────────────
	sampleVerify := "PASS"
	if len(sampleIDs) > 0 {
		if err = verifySample(ctx, sqliteDB, pool, sampleIDs); err != nil {
			sampleVerify = "FAIL: " + err.Error()
		}
	} else {
		sampleVerify = "SKIP (0 rows read)"
	}

	// ── Row-count comparison ───────────────────────────────────────────────────
	var pgCount int
	if err = pool.QueryRow(ctx, `SELECT COUNT(*) FROM vault.credentials`).Scan(&pgCount); err != nil {
		log.Printf("vault-migrate: WARNING could not count postgres rows: %v", err)
	}

	countNote := fmt.Sprintf("%d", pgCount)
	if pgCount == o.read {
		countNote += " (matches sqlite)"
	} else {
		countNote += fmt.Sprintf(" (WARNING: sqlite has %d; postgres has %d — possible pre-existing rows or partial state)", o.read, pgCount)
	}

	// ── Print summary ──────────────────────────────────────────────────────────
	fmt.Printf("\nMigration summary:\n")
	fmt.Printf("  Source (sqlite):     %s\n", sqlitePath)
	fmt.Printf("  Target (postgres):   %s\n", redactDSN(pgDSN))
	fmt.Printf("  Read from sqlite:    %d\n", o.read)
	fmt.Printf("  Inserted:            %d\n", o.inserted)
	fmt.Printf("  Skipped (conflict):  %d\n", o.skippedConflict)
	fmt.Printf("  Errors:              %d\n", o.errors)
	fmt.Printf("  Sample verify (%d):   %s\n", len(sampleIDs), sampleVerify)
	fmt.Printf("  Postgres row count:  %s\n", countNote)

	if o.errors > 0 || sampleVerify != "PASS" {
		fmt.Printf("\n✗ Migration completed with errors. Review log output above.\n")
		return fmt.Errorf("migration finished with %d errors; sample verify: %s", o.errors, sampleVerify)
	}

	fmt.Printf("\n✓ Migration complete. To cut over, restart vault-adapter:\n")
	fmt.Printf("    docker compose up -d --no-deps --force-recreate vault-adapter\n")
	return nil
}

// insertRow inserts one row into postgres.
// Returns (true, nil) on insert, (false, nil) on conflict-skip, (false, err) on error.
func insertRow(ctx context.Context, pool *pgxpool.Pool, r sqliteRow) (inserted bool, err error) {
	// Validate tenant_id and service_id as UUIDs (postgres rejects malformed UUID strings).
	if _, err = uuid.Parse(r.tenantID); err != nil {
		return false, fmt.Errorf("malformed tenant_id %q: %w", r.tenantID, err)
	}
	if _, err = uuid.Parse(r.serviceID); err != nil {
		return false, fmt.Errorf("malformed service_id %q: %w", r.serviceID, err)
	}

	// Convert sqlite integer booleans to Go booleans.
	isCurrent := r.isCurrent != 0
	isRevoked := r.isRevoked != 0

	// Batch by tenant: acquire a single connection, begin a transaction,
	// set RLS tenant GUC, insert, commit.
	conn, err := pool.Acquire(ctx)
	if err != nil {
		return false, fmt.Errorf("acquire pg conn: %w", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return false, fmt.Errorf("begin pg tx: %w", err)
	}
	defer func() {
		if err != nil {
			_ = tx.Rollback(ctx)
		}
	}()

	// Set RLS GUC for this transaction — mirror of production PostgresStore.Put.
	if _, err = tx.Exec(ctx,
		"SELECT set_config('app.current_tenant', $1, true)", r.tenantID,
	); err != nil {
		return false, fmt.Errorf("set tenant GUC: %w", err)
	}

	tag, err := tx.Exec(ctx, `
		INSERT INTO vault.credentials (
			credential_id, tenant_id, service_id, key_version, auth_scheme,
			wrapped_dek, enc_payload, is_current, is_revoked, created_at,
			target_url, header_name, query_param
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
		ON CONFLICT (credential_id) DO NOTHING
	`,
		r.credentialID, r.tenantID, r.serviceID, r.keyVersion, r.authScheme,
		r.wrappedDEK, r.encPayload, isCurrent, isRevoked, r.createdAt,
		r.targetURL, r.headerName, r.queryParam,
	)
	if err != nil {
		return false, fmt.Errorf("insert credential_id=%q: %w", r.credentialID, err)
	}

	if err = tx.Commit(ctx); err != nil {
		return false, fmt.Errorf("commit: %w", err)
	}

	return tag.RowsAffected() == 1, nil
}

// verifySample fetches 5 random credential_ids from both sqlite and postgres
// and byte-compares wrapped_dek, enc_payload, and auth_scheme.
func verifySample(ctx context.Context, sqliteDB *sql.DB, pool *pgxpool.Pool, ids []string) error {
	for _, id := range ids {
		// Fetch from sqlite.
		var wrappedDEKSQ, encPayloadSQ []byte
		var authSchemeSQ int64
		var tenantIDSQ string
		err := sqliteDB.QueryRowContext(ctx, `
			SELECT tenant_id, auth_scheme, wrapped_dek, enc_payload
			  FROM credentials
			 WHERE credential_id = ?
		`, id).Scan(&tenantIDSQ, &authSchemeSQ, &wrappedDEKSQ, &encPayloadSQ)
		if err != nil {
			return fmt.Errorf("sqlite fetch %q: %w", id, err)
		}

		// Fetch from postgres (needs tenant GUC for RLS).
		conn, err := pool.Acquire(ctx)
		if err != nil {
			return fmt.Errorf("acquire pg conn for verify: %w", err)
		}

		var wrappedDEKPG, encPayloadPG []byte
		var authSchemePG int32
		verifyErr := func() error {
			defer conn.Release()

			tx, txErr := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
			if txErr != nil {
				return fmt.Errorf("begin tx for verify: %w", txErr)
			}
			defer func() { _ = tx.Rollback(ctx) }()

			if _, txErr = tx.Exec(ctx,
				"SELECT set_config('app.current_tenant', $1, true)", tenantIDSQ,
			); txErr != nil {
				return fmt.Errorf("set tenant GUC for verify: %w", txErr)
			}

			txErr = tx.QueryRow(ctx, `
				SELECT auth_scheme, wrapped_dek, enc_payload
				  FROM vault.credentials
				 WHERE credential_id = $1
			`, id).Scan(&authSchemePG, &wrappedDEKPG, &encPayloadPG)
			if errors.Is(txErr, pgx.ErrNoRows) {
				return fmt.Errorf("credential_id %q not found in postgres", id)
			}
			if txErr != nil {
				return fmt.Errorf("pg fetch %q: %w", id, txErr)
			}

			_ = tx.Commit(ctx)
			return nil
		}()
		if verifyErr != nil {
			return verifyErr
		}

		// Byte-compare (don't log blob contents — encrypted but still sensitive).
		if int64(authSchemePG) != authSchemeSQ {
			return fmt.Errorf("credential_id %q: auth_scheme mismatch (sqlite=%d pg=%d)",
				id, authSchemeSQ, authSchemePG)
		}
		if !bytes.Equal(wrappedDEKSQ, wrappedDEKPG) {
			return fmt.Errorf("credential_id %q: wrapped_dek mismatch (sqlite len=%d pg len=%d)",
				id, len(wrappedDEKSQ), len(wrappedDEKPG))
		}
		if !bytes.Equal(encPayloadSQ, encPayloadPG) {
			return fmt.Errorf("credential_id %q: enc_payload mismatch (sqlite len=%d pg len=%d)",
				id, len(encPayloadSQ), len(encPayloadPG))
		}
	}
	return nil
}

// reservoirSample returns up to k randomly-chosen items from items (Knuth shuffle).
// Uses a deterministic seed from current time so results differ between runs.
func reservoirSample(items []string, k int) []string {
	if len(items) == 0 {
		return nil
	}
	rng := rand.New(rand.NewSource(time.Now().UnixNano())) //nolint:gosec // non-security use
	n := len(items)
	if n <= k {
		out := make([]string, n)
		copy(out, items)
		return out
	}
	// reservoir
	out := make([]string, k)
	copy(out, items[:k])
	for i := k; i < n; i++ {
		j := rng.Intn(i + 1)
		if j < k {
			out[j] = items[i]
		}
	}
	return out
}

// redactDSN removes the password from a postgres DSN for safe log output.
func redactDSN(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		// Fallback: replace password in libpq key=value style (best-effort).
		return "<dsn-parse-error>"
	}
	if u.User != nil {
		if _, hasPass := u.User.Password(); hasPass {
			u.User = url.UserPassword(u.User.Username(), "***")
		}
	}
	return u.String()
}
