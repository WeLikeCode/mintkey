// Command vault-migrate-pg-to-hashicorp copies every credential row from the
// Postgres vault.credentials table into HashiCorp Vault KV v2.
//
// The migration is IDEMPOTENT: a version that already exists in HashiCorp Vault
// (identified by a successful Get) is skipped.
//
// Usage:
//
//	MINTKEY_VAULT_PG_DSN="postgres://..." \
//	MINTKEY_VAULT_HASHICORP_ADDR=http://hashicorp-vault:8201 \
//	MINTKEY_VAULT_HASHICORP_ROLE_ID=<role_id> \
//	MINTKEY_VAULT_HASHICORP_SECRET_ID=<secret_id> \
//	go run ./cmd/vault-migrate-pg-to-hashicorp/...
//
// Flags (override env vars):
//
//	--pg-dsn          postgres DSN
//	--hcp-addr        HashiCorp Vault address
//	--hcp-mount       KV v2 mount (default: secret)
//	--hcp-prefix      KV v2 path prefix (default: mintkey)
//	--hcp-role-id     AppRole role_id
//	--hcp-secret-id   AppRole secret_id
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

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
)

// migrationOutcomes tracks migration counters.
type migrationOutcomes struct {
	read     int
	inserted int
	skipped  int
	errors   int
}

func main() {
	pgDSN := flag.String("pg-dsn", os.Getenv("MINTKEY_VAULT_PG_DSN"), "postgres DSN")
	hcpAddr := flag.String("hcp-addr", os.Getenv("MINTKEY_VAULT_HASHICORP_ADDR"), "HashiCorp Vault address")
	hcpMount := flag.String("hcp-mount", getEnvOr("MINTKEY_VAULT_HASHICORP_MOUNT", "secret"), "KV v2 mount")
	hcpPrefix := flag.String("hcp-prefix", getEnvOr("MINTKEY_VAULT_HASHICORP_PREFIX", "mintkey"), "KV v2 path prefix")
	hcpRoleID := flag.String("hcp-role-id", os.Getenv("MINTKEY_VAULT_HASHICORP_ROLE_ID"), "AppRole role_id")
	hcpSecretID := flag.String("hcp-secret-id", os.Getenv("MINTKEY_VAULT_HASHICORP_SECRET_ID"), "AppRole secret_id")
	flag.Parse()

	if *pgDSN == "" {
		log.Fatal("vault-migrate-pg-to-hashicorp: MINTKEY_VAULT_PG_DSN (or --pg-dsn) is required")
	}
	if *hcpAddr == "" {
		log.Fatal("vault-migrate-pg-to-hashicorp: MINTKEY_VAULT_HASHICORP_ADDR (or --hcp-addr) is required")
	}
	if *hcpRoleID == "" {
		log.Fatal("vault-migrate-pg-to-hashicorp: MINTKEY_VAULT_HASHICORP_ROLE_ID (or --hcp-role-id) is required")
	}
	if *hcpSecretID == "" {
		log.Fatal("vault-migrate-pg-to-hashicorp: MINTKEY_VAULT_HASHICORP_SECRET_ID (or --hcp-secret-id) is required")
	}

	hcpCfg := store.HashiCorpConfig{
		Addr:     *hcpAddr,
		Mount:    *hcpMount,
		Prefix:   *hcpPrefix,
		RoleID:   *hcpRoleID,
		SecretID: *hcpSecretID,
	}

	ctx := context.Background()
	if err := run(ctx, *pgDSN, hcpCfg); err != nil {
		log.Fatalf("vault-migrate-pg-to-hashicorp: %v", err)
	}
}

func run(ctx context.Context, pgDSN string, hcpCfg store.HashiCorpConfig) error {
	_, err := runWithOutcomes(ctx, pgDSN, hcpCfg)
	return err
}

func runWithOutcomes(ctx context.Context, pgDSN string, hcpCfg store.HashiCorpConfig) (migrationOutcomes, error) {
	// ── Open Postgres ──────────────────────────────────────────────────────────
	cfg, err := pgxpool.ParseConfig(pgDSN)
	if err != nil {
		return migrationOutcomes{}, fmt.Errorf("parse pg dsn: %w", err)
	}
	cfg.MaxConns = 5
	cfg.MinConns = 1

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return migrationOutcomes{}, fmt.Errorf("create pg pool: %w", err)
	}
	defer pool.Close()

	if err = pool.Ping(ctx); err != nil {
		return migrationOutcomes{}, fmt.Errorf("ping postgres: %w", err)
	}

	// ── Open HashiCorp Vault ───────────────────────────────────────────────────
	hcpSt, err := store.NewHashiCorp(ctx, hcpCfg)
	if err != nil {
		return migrationOutcomes{}, fmt.Errorf("connect to hashicorp vault: %w", err)
	}
	defer hcpSt.Close()

	// ── Read all rows from Postgres ────────────────────────────────────────────
	rows, err := pool.Query(ctx, `
		SELECT credential_id, tenant_id, service_id, key_version, auth_scheme,
		       wrapped_dek, enc_payload, is_current, is_revoked, created_at,
		       target_url, header_name, query_param, target_address, ssh_user
		  FROM vault.credentials
		 ORDER BY tenant_id, service_id, key_version
	`)
	if err != nil {
		return migrationOutcomes{}, fmt.Errorf("query postgres credentials: %w", err)
	}
	defer rows.Close()

	var o migrationOutcomes
	var allCredIDs []string       // for reservoir sampling
	var allTenantIDs []string     // parallel to allCredIDs
	var allServiceIDs []string
	var allVersions []uint32

	// Group-level idempotency: once we see that an entire (tenant, service) group
	// is already in HCP (v1 exists), skip every remaining row in that group without
	// calling Put again. Reset when the group changes.
	var skipGroup string // "<tenantID>/<serviceID>" of the group currently being skipped

	for rows.Next() {
		var (
			credentialID  string
			tenantID      string
			serviceID     string
			keyVersion    int32
			authScheme    int32
			wrappedDEK    []byte
			encPayload    []byte
			isCurrent     bool
			isRevoked     bool
			createdAt     int64
			targetURL     string
			headerName    string
			queryParam    string
			targetAddress string
			sshUser       string
		)
		if err = rows.Scan(
			&credentialID, &tenantID, &serviceID,
			&keyVersion, &authScheme,
			&wrappedDEK, &encPayload,
			&isCurrent, &isRevoked, &createdAt,
			&targetURL, &headerName, &queryParam,
			&targetAddress, &sshUser,
		); err != nil {
			return migrationOutcomes{}, fmt.Errorf("scan postgres row: %w", err)
		}

		o.read++
		allCredIDs = append(allCredIDs, credentialID)
		allTenantIDs = append(allTenantIDs, tenantID)
		allServiceIDs = append(allServiceIDs, serviceID)
		allVersions = append(allVersions, uint32(keyVersion))

		groupKey := tenantID + "/" + serviceID

		// Group-level idempotency: if we already determined this group exists in HCP,
		// skip without any further Vault calls.
		if skipGroup == groupKey {
			o.skipped++
			continue
		}
		// Reset skip tracking when the group changes (rows are ordered by tenant, service, version).
		if skipGroup != "" && skipGroup != groupKey {
			skipGroup = ""
		}

		// On the first row of each group (key_version == 1 after ordering ASC),
		// check if v1 already exists in HCP. If it does, mark the whole group as done.
		if uint32(keyVersion) == 1 {
			existing, getErr := hcpSt.Get(ctx, tenantID, serviceID, 1)
			if getErr == nil && existing != nil {
				// v1 exists — the whole group was already migrated; skip.
				skipGroup = groupKey
				o.skipped++
				continue
			}
			if getErr != nil && !errors.Is(getErr, sql.ErrNoRows) {
				log.Printf("vault-migrate: WARNING check existence for %q v%d: %v", credentialID, keyVersion, getErr)
				// Treat unexpected errors as not-found → proceed with insert.
			}
		}

		rec := store.CredentialRecord{
			CredentialID:  credentialID,
			TenantID:      tenantID,
			ServiceID:     serviceID,
			AuthScheme:    authScheme,
			WrappedDEK:    wrappedDEK,
			EncPayload:    encPayload,
			IsCurrent:     isCurrent,
			IsRevoked:     isRevoked,
			CreatedAt:     createdAt,
			TargetURL:     targetURL,
			HeaderName:    headerName,
			QueryParam:    queryParam,
			TargetAddress: targetAddress,
			SSHUser:       sshUser,
		}

		// We need to write the exact key_version, but Put() auto-assigns the next version.
		// Use the raw put path directly via the store's internal index-aware write.
		// Since HashiCorpStore.Put always assigns max+1, for migration we need a special approach:
		// write each version in order so that the assigned version matches the source version.
		// Because rows are ordered by (tenant_id, service_id, key_version) ASC, consecutive
		// calls to Put for the same (tenant,service) will assign monotonically increasing versions.
		// This matches the source order, so this works for ordered migration.
		assignedVer, putErr := hcpSt.Put(ctx, rec)
		if putErr != nil {
			log.Printf("vault-migrate: ERROR inserting %q v%d: %v", credentialID, keyVersion, putErr)
			o.errors++
			continue
		}
		if assignedVer != uint32(keyVersion) {
			log.Printf("vault-migrate: WARNING credential_id=%q: assigned v%d but source was v%d",
				credentialID, assignedVer, keyVersion)
		}
		o.inserted++
	}
	if err = rows.Err(); err != nil {
		return migrationOutcomes{}, fmt.Errorf("iterate postgres rows: %w", err)
	}

	// ── 5-sample reservoir verification ───────────────────────────────────────
	sampleIdx := reservoirSampleIdx(len(allCredIDs), 5)
	sampleVerify := "SKIP (0 rows read)"
	if len(sampleIdx) > 0 {
		verifyErr := verifySamplePgToHCP(ctx, pool, hcpSt, sampleIdx, allCredIDs, allTenantIDs, allServiceIDs, allVersions)
		if verifyErr != nil {
			sampleVerify = "FAIL: " + verifyErr.Error()
		} else {
			sampleVerify = "PASS"
		}
	}

	// ── Row count comparison ───────────────────────────────────────────────────
	var pgCount int
	if err = pool.QueryRow(ctx, `SELECT COUNT(*) FROM vault.credentials`).Scan(&pgCount); err != nil {
		log.Printf("vault-migrate: WARNING could not count postgres rows: %v", err)
	}

	// ── Print summary ──────────────────────────────────────────────────────────
	fmt.Printf("\nMigration summary (postgres → hashicorp-vault):\n")
	fmt.Printf("  Source (postgres):    %s\n", redactDSN(pgDSN))
	fmt.Printf("  Target (hashicorp):   %s\n", hcpCfg.Addr)
	fmt.Printf("  Read from postgres:   %d\n", o.read)
	fmt.Printf("  Inserted:             %d\n", o.inserted)
	fmt.Printf("  Skipped (exists):     %d\n", o.skipped)
	fmt.Printf("  Errors:               %d\n", o.errors)
	fmt.Printf("  Sample verify (%d):    %s\n", len(sampleIdx), sampleVerify)
	fmt.Printf("  Postgres row count:   %d\n", pgCount)

	if o.errors > 0 || sampleVerify == "FAIL" || (len(sampleIdx) > 0 && sampleVerify != "PASS") {
		fmt.Printf("\n✗ Migration completed with errors. Review log output above.\n")
		return o, fmt.Errorf("migration finished with %d errors; sample verify: %s", o.errors, sampleVerify)
	}

	fmt.Printf("\n✓ Migration complete. To cut over:\n")
	fmt.Printf("  Set MINTKEY_VAULT_BACKEND=hashicorp and restart vault-adapter:\n")
	fmt.Printf("    docker compose up -d --no-deps --force-recreate vault-adapter\n")
	return o, nil
}

// verifySamplePgToHCP fetches rows from both Postgres and HashiCorp and byte-compares
// wrapped_dek, enc_payload, and auth_scheme.
func verifySamplePgToHCP(
	ctx context.Context,
	pool *pgxpool.Pool,
	hcpSt *store.HashiCorpStore,
	idxs []int,
	credIDs, tenantIDs, serviceIDs []string,
	versions []uint32,
) error {
	for _, idx := range idxs {
		credID := credIDs[idx]
		tenantID := tenantIDs[idx]
		serviceID := serviceIDs[idx]
		ver := versions[idx]

		// Fetch from Postgres (set tenant GUC for RLS).
		conn, err := pool.Acquire(ctx)
		if err != nil {
			return fmt.Errorf("acquire pg conn for verify: %w", err)
		}

		var pgWrappedDEK, pgEncPayload []byte
		var pgAuthScheme int32
		var pgTargetAddress, pgSSHUser string
		verifyErr := func() error {
			defer conn.Release()
			tx, txErr := conn.BeginTx(ctx, pgx.TxOptions{AccessMode: pgx.ReadOnly})
			if txErr != nil {
				return fmt.Errorf("begin tx: %w", txErr)
			}
			defer func() { _ = tx.Rollback(ctx) }()

			if _, txErr = tx.Exec(ctx,
				"SELECT set_config('app.current_tenant', $1, true)", tenantID,
			); txErr != nil {
				// RLS GUC may fail in test DBs without RLS; tolerate.
				_ = txErr
			}

			txErr = tx.QueryRow(ctx, `
				SELECT auth_scheme, wrapped_dek, enc_payload, target_address, ssh_user
				  FROM vault.credentials
				 WHERE credential_id = $1
			`, credID).Scan(&pgAuthScheme, &pgWrappedDEK, &pgEncPayload, &pgTargetAddress, &pgSSHUser)
			if errors.Is(txErr, pgx.ErrNoRows) {
				return fmt.Errorf("credential_id %q not found in postgres", credID)
			}
			if txErr != nil {
				return fmt.Errorf("pg fetch %q: %w", credID, txErr)
			}
			_ = tx.Commit(ctx)
			return nil
		}()
		if verifyErr != nil {
			return verifyErr
		}

		// Fetch from HashiCorp Vault.
		hcpRec, err := hcpSt.Get(ctx, tenantID, serviceID, ver)
		if err != nil {
			return fmt.Errorf("hcp Get %q v%d: %w", credID, ver, err)
		}

		// Byte-compare.
		if int32(hcpRec.AuthScheme) != pgAuthScheme {
			return fmt.Errorf("credential_id %q: auth_scheme mismatch (pg=%d hcp=%d)",
				credID, pgAuthScheme, hcpRec.AuthScheme)
		}
		if !bytes.Equal(pgWrappedDEK, hcpRec.WrappedDEK) {
			return fmt.Errorf("credential_id %q: wrapped_dek mismatch (pg len=%d hcp len=%d)",
				credID, len(pgWrappedDEK), len(hcpRec.WrappedDEK))
		}
		if !bytes.Equal(pgEncPayload, hcpRec.EncPayload) {
			return fmt.Errorf("credential_id %q: enc_payload mismatch (pg len=%d hcp len=%d)",
				credID, len(pgEncPayload), len(hcpRec.EncPayload))
		}
		if pgTargetAddress != hcpRec.TargetAddress {
			return fmt.Errorf("credential_id %q: target_address mismatch (pg=%q hcp=%q)",
				credID, pgTargetAddress, hcpRec.TargetAddress)
		}
		if pgSSHUser != hcpRec.SSHUser {
			return fmt.Errorf("credential_id %q: ssh_user mismatch (pg=%q hcp=%q)",
				credID, pgSSHUser, hcpRec.SSHUser)
		}
	}
	return nil
}

// reservoirSampleIdx returns up to k randomly-chosen indices from [0, n).
func reservoirSampleIdx(n, k int) []int {
	if n == 0 {
		return nil
	}
	rng := rand.New(rand.NewSource(time.Now().UnixNano())) //nolint:gosec // non-security
	if n <= k {
		out := make([]int, n)
		for i := range out {
			out[i] = i
		}
		return out
	}
	out := make([]int, k)
	for i := range out {
		out[i] = i
	}
	for i := k; i < n; i++ {
		j := rng.Intn(i + 1)
		if j < k {
			out[j] = i
		}
	}
	return out
}

// redactDSN removes the password from a postgres DSN for safe log output.
func redactDSN(dsn string) string {
	u, err := url.Parse(dsn)
	if err != nil {
		return "<dsn-parse-error>"
	}
	if u.User != nil {
		if _, hasPass := u.User.Password(); hasPass {
			u.User = url.UserPassword(u.User.Username(), "***")
		}
	}
	return u.String()
}

// getEnvOr returns the env var value or the fallback.
func getEnvOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
