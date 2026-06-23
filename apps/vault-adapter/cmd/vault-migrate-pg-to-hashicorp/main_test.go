//go:build integration

package main

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/testcontainers/testcontainers-go"
	tcpostgres "github.com/testcontainers/testcontainers-go/modules/postgres"
	"github.com/testcontainers/testcontainers-go/wait"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
)

const (
	pgImage      = "postgres:16"
	vaultImage   = "hashicorp/vault:1.18"
	vaultToken   = "test-migrate-token"
	vaultPort    = "8200"
)

// startPostgres spins up a Postgres container, runs the vault schema DDL, and
// returns a connection pool + cleanup function.
func startPostgres(t *testing.T) (*pgxpool.Pool, func()) {
	t.Helper()
	ctx := context.Background()

	pgctr, err := tcpostgres.Run(ctx, pgImage,
		tcpostgres.WithDatabase("testdb"),
		tcpostgres.WithUsername("testuser"),
		tcpostgres.WithPassword("testpass"),
		testcontainers.WithWaitStrategy(
			wait.ForLog("database system is ready to accept connections").
				WithOccurrence(2).
				WithStartupTimeout(60*time.Second),
		),
	)
	if err != nil {
		t.Fatalf("start postgres: %v", err)
	}

	connStr, err := pgctr.ConnectionString(ctx, "sslmode=disable")
	if err != nil {
		_ = pgctr.Terminate(ctx)
		t.Fatalf("pg connection string: %v", err)
	}

	pool, err := pgxpool.New(ctx, connStr)
	if err != nil {
		_ = pgctr.Terminate(ctx)
		t.Fatalf("pg pool: %v", err)
	}

	// Apply vault.credentials schema (matching 018-vault-schema.yaml).
	schema := `
CREATE SCHEMA IF NOT EXISTS vault;
CREATE TABLE IF NOT EXISTS vault.credentials (
    credential_id TEXT        PRIMARY KEY,
    tenant_id     UUID        NOT NULL,
    service_id    UUID        NOT NULL,
    key_version   INTEGER     NOT NULL,
    auth_scheme   INTEGER     NOT NULL DEFAULT 0,
    wrapped_dek   BYTEA       NOT NULL,
    enc_payload   BYTEA       NOT NULL,
    is_current    BOOLEAN     NOT NULL DEFAULT TRUE,
    is_revoked    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at    BIGINT      NOT NULL,
    target_url    TEXT        NOT NULL DEFAULT '',
    header_name   TEXT        NOT NULL DEFAULT '',
    query_param   TEXT        NOT NULL DEFAULT '',
    UNIQUE (tenant_id, service_id, key_version)
);
`
	if _, err = pool.Exec(ctx, schema); err != nil {
		pool.Close()
		_ = pgctr.Terminate(ctx)
		t.Fatalf("apply schema: %v", err)
	}

	cleanup := func() {
		pool.Close()
		_ = pgctr.Terminate(context.Background())
	}
	return pool, cleanup
}

// startMigrateVault spins up a HashiCorp Vault container with AppRole configured
// for the migration test.
func startMigrateVault(t *testing.T) (string, string, string, func()) {
	t.Helper()
	ctx := context.Background()

	req := testcontainers.ContainerRequest{
		Image:        vaultImage,
		ExposedPorts: []string{vaultPort + "/tcp"},
		Env: map[string]string{
			"VAULT_DEV_ROOT_TOKEN_ID":  vaultToken,
			"VAULT_DEV_LISTEN_ADDRESS": "0.0.0.0:" + vaultPort,
		},
		Cmd: []string{"server", "-dev", "-dev-listen-address=0.0.0.0:" + vaultPort},
		WaitingFor: wait.ForHTTP("/v1/sys/health").
			WithPort(vaultPort + "/tcp").
			WithStartupTimeout(60 * time.Second),
	}

	ctr, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: req,
		Started:          true,
	})
	if err != nil {
		t.Fatalf("start vault container: %v", err)
	}

	mappedPort, err := ctr.MappedPort(ctx, vaultPort)
	if err != nil {
		_ = ctr.Terminate(ctx)
		t.Fatalf("get mapped port: %v", err)
	}
	host, err := ctr.Host(ctx)
	if err != nil {
		_ = ctr.Terminate(ctx)
		t.Fatalf("get host: %v", err)
	}

	addr := fmt.Sprintf("http://%s:%s", host, mappedPort.Port())

	// Configure AppRole.
	roleID, secretID := setupMigrateAppRole(t, addr)

	cleanup := func() { _ = ctr.Terminate(context.Background()) }
	return addr, roleID, secretID, cleanup
}

// setupMigrateAppRole configures AppRole in the vault container for migration tests.
func setupMigrateAppRole(t *testing.T, addr string) (string, string) {
	t.Helper()
	call := func(method, path string, body any) map[string]any {
		return vaultHTTPMigrate(t, addr, method, path, body)
	}

	call(http.MethodPost, "/v1/sys/auth/approle", map[string]any{"type": "approle"})

	policyHCL := `path "secret/data/mintkey/*" { capabilities = ["create","read","update","delete","list"] }
path "secret/metadata/mintkey/*" { capabilities = ["read","list","delete"] }`
	call(http.MethodPost, "/v1/sys/policies/acl/mintkey", map[string]any{"policy": policyHCL})

	call(http.MethodPost, "/v1/auth/approle/role/mintkey", map[string]any{
		"token_ttl":     "20m",
		"token_max_ttl": "1h",
		"policies":      []string{"mintkey"},
	})

	result := call(http.MethodGet, "/v1/auth/approle/role/mintkey/role-id", nil)
	roleID, _ := result["data"].(map[string]any)["role_id"].(string)

	result = call(http.MethodPost, "/v1/auth/approle/role/mintkey/secret-id", nil)
	secretID, _ := result["data"].(map[string]any)["secret_id"].(string)

	return roleID, secretID
}

// vaultHTTPMigrate is a minimal Vault HTTP helper used by the migration test.
func vaultHTTPMigrate(t *testing.T, addr, method, path string, body any) map[string]any {
	t.Helper()
	var bodyBytes []byte
	if body != nil {
		import_bytes, _ := marshalJSON(body)
		bodyBytes = import_bytes
	}
	req, _ := http.NewRequestWithContext(context.Background(), method, addr+path, bytes.NewReader(bodyBytes))
	req.Header.Set("X-Vault-Token", vaultToken)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("vault HTTP %s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	var result map[string]any
	if resp.StatusCode < 400 {
		_ = decodeJSON(resp.Body, &result)
	}
	return result
}

// TestMigratePostgresToHashiCorp is the full TDD integration test for the migration command.
func TestMigratePostgresToHashiCorp(t *testing.T) {
	ctx := context.Background()

	// Start Postgres + seed it.
	pool, pgCleanup := startPostgres(t)
	defer pgCleanup()

	// Start HashiCorp Vault + configure AppRole.
	vaultAddr, roleID, secretID, vaultCleanup := startMigrateVault(t)
	defer vaultCleanup()

	pgConnStr, err := pool.Config().ConnString(), error(nil)
	_ = err
	// pgxpool.Pool.Config().ConnString() — but pgxpool doesn't expose this directly.
	// We need to get the DSN from the container. Re-derive from pool config.
	pgDSN := pool.Config().ConnConfig.ConnString()

	hcpCfg := store.HashiCorpConfig{
		Addr:     vaultAddr,
		Mount:    "secret",
		Prefix:   "mintkey",
		RoleID:   roleID,
		SecretID: secretID,
	}

	// Fixed tenant/service UUIDs for RLS GUC (no actual RLS in test DB but we match production discipline).
	const (
		tenantID  = "00000000-0000-0000-0000-000000000001"
		serviceID = "00000000-0000-0000-0000-000000000002"
	)

	// Seed 10 rows into vault.credentials.
	for i := 1; i <= 10; i++ {
		_, err := pool.Exec(ctx, `
			INSERT INTO vault.credentials (credential_id, tenant_id, service_id, key_version,
				auth_scheme, wrapped_dek, enc_payload, is_current, is_revoked, created_at, target_url, header_name, query_param)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, '', '', '')
		`,
			fmt.Sprintf("cred_migrate_%02d", i),
			tenantID,
			serviceID,
			i,
			1,
			[]byte(fmt.Sprintf("dek-%02d", i)),
			[]byte(fmt.Sprintf("payload-%02d", i)),
			i == 10, // only the last one is current
			false,
			time.Now().UnixNano(),
		)
		if err != nil {
			t.Fatalf("seed row %d: %v", i, err)
		}
	}

	// Run migration.
	if err := run(ctx, pgDSN, hcpCfg); err != nil {
		t.Fatalf("run migration: %v", err)
	}

	// Verify: check 5 rows by credential_id match.
	hcpSt, err := store.NewHashiCorp(ctx, hcpCfg)
	if err != nil {
		t.Fatalf("NewHashiCorp for verify: %v", err)
	}
	defer hcpSt.Close()

	// Sample verify: check rows 1, 3, 5, 7, 9.
	sampleVersions := []uint32{1, 3, 5, 7, 9}
	for _, ver := range sampleVersions {
		rec, err := hcpSt.Get(ctx, tenantID, serviceID, ver)
		if err != nil {
			t.Errorf("Get v%d from HCP: %v", ver, err)
			continue
		}
		expectedDEK := []byte(fmt.Sprintf("dek-%02d", ver))
		expectedPayload := []byte(fmt.Sprintf("payload-%02d", ver))
		if !bytes.Equal(rec.WrappedDEK, expectedDEK) {
			t.Errorf("v%d: WrappedDEK mismatch: got %q, want %q", ver, rec.WrappedDEK, expectedDEK)
		}
		if !bytes.Equal(rec.EncPayload, expectedPayload) {
			t.Errorf("v%d: EncPayload mismatch: got %q, want %q", ver, rec.EncPayload, expectedPayload)
		}
	}

	// Idempotency check — run again, should skip all 10.
	outcomes2, err := runWithOutcomes(ctx, pgDSN, hcpCfg)
	if err != nil {
		t.Fatalf("second run: %v", err)
	}
	if outcomes2.inserted != 0 {
		t.Errorf("second run: inserted %d, want 0 (all should be skipped)", outcomes2.inserted)
	}
	if outcomes2.skipped != 10 {
		t.Errorf("second run: skipped %d, want 10", outcomes2.skipped)
	}
	if outcomes2.errors != 0 {
		t.Errorf("second run: errors %d, want 0", outcomes2.errors)
	}
	_ = pgConnStr
}
