//go:build postgres

// Run with a live Postgres:
//
//	MINTKEY_TEST_PG_DSN="postgres://..." go test -tags postgres -v -count=1 -race ./internal/store/...
//
// RLS tests additionally require MINTKEY_TEST_PG_APP_DSN set to a connection
// string using the mintkey_app role (rolsuper=f, rolbypassrls=f).  Without it
// the RLS tests are skipped with an explanatory message.
//
// IMPORTANT: These tests assume Liquibase changelog 027 has been applied
// (vault.agent_secrets table exists).  Run `make dev-test` first.
package store

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// agentSecretTenantID / secretIDPrefix are fixed test values that are cleaned
// up before and after each test so the DB stays hermetic.
const (
	agentSecretTestTenant = "aaaaaaaa-0000-0000-0000-000000000001"
)

// cleanupAgentSecrets removes all vault.agent_secrets rows for the test tenant.
func cleanupAgentSecrets(t *testing.T, pool *pgxpool.Pool, tenantID string) {
	t.Helper()
	ctx := context.Background()
	conn, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("cleanupAgentSecrets: acquire: %v", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		t.Fatalf("cleanupAgentSecrets: begin tx: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		t.Fatalf("cleanupAgentSecrets: set tenant: %v", err)
	}
	if _, err = tx.Exec(ctx,
		`DELETE FROM vault.agent_secrets WHERE tenant_id = $1`, tenantID,
	); err != nil {
		t.Fatalf("cleanupAgentSecrets: delete: %v", err)
	}
	if err = tx.Commit(ctx); err != nil {
		t.Fatalf("cleanupAgentSecrets: commit: %v", err)
	}
}

// TestPostgresAgentSecret_PutGetDeleteRoundTrip verifies the full lifecycle.
func TestPostgresAgentSecret_PutGetDeleteRoundTrip(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	tenantID := agentSecretTestTenant
	secretID := "sec_pgtest_001_aaaaaaaaaaaaaaaaaaaaaa"

	cleanupAgentSecrets(t, s.pool, tenantID)
	t.Cleanup(func() { cleanupAgentSecrets(t, s.pool, tenantID) })

	rec := AgentSecretRecord{
		SecretID:   secretID,
		TenantID:   tenantID,
		KeyVersion: 1,
		WrappedDEK: []byte("wrapped-dek-bytes"),
		EncPayload: []byte("encrypted-payload-bytes"),
	}

	// PUT.
	if err := s.PutAgentSecret(ctx, rec); err != nil {
		t.Fatalf("PutAgentSecret: %v", err)
	}

	// GET.
	got, err := s.GetAgentSecret(ctx, tenantID, secretID)
	if err != nil {
		t.Fatalf("GetAgentSecret: %v", err)
	}
	if got.SecretID != secretID {
		t.Errorf("SecretID = %q; want %q", got.SecretID, secretID)
	}
	if got.TenantID != tenantID {
		t.Errorf("TenantID = %q; want %q", got.TenantID, tenantID)
	}
	if string(got.WrappedDEK) != string(rec.WrappedDEK) {
		t.Error("WrappedDEK mismatch")
	}
	if string(got.EncPayload) != string(rec.EncPayload) {
		t.Error("EncPayload mismatch")
	}
	if got.CreatedAt.IsZero() {
		t.Error("CreatedAt should be set")
	}
	if got.UpdatedAt.IsZero() {
		t.Error("UpdatedAt should be set")
	}

	// DELETE.
	if err := s.DeleteAgentSecret(ctx, tenantID, secretID); err != nil {
		t.Fatalf("DeleteAgentSecret: %v", err)
	}

	// GET after DELETE should be not-found.
	_, err = s.GetAgentSecret(ctx, tenantID, secretID)
	if err == nil {
		t.Fatal("expected error after delete, got nil")
	}
	if !errors.Is(err, ErrAgentSecretNotFound) {
		t.Errorf("expected ErrAgentSecretNotFound, got %v", err)
	}
}

// TestPostgresAgentSecret_PutOverwrite verifies upsert semantics: a second PUT
// replaces wrapped_dek and enc_payload and advances updated_at.
func TestPostgresAgentSecret_PutOverwrite(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	tenantID := agentSecretTestTenant
	secretID := "sec_pgtest_002_aaaaaaaaaaaaaaaaaaaaaa"

	cleanupAgentSecrets(t, s.pool, tenantID)
	t.Cleanup(func() { cleanupAgentSecrets(t, s.pool, tenantID) })

	rec1 := AgentSecretRecord{
		SecretID:   secretID,
		TenantID:   tenantID,
		KeyVersion: 1,
		WrappedDEK: []byte("dek-v1"),
		EncPayload: []byte("payload-v1"),
	}
	if err := s.PutAgentSecret(ctx, rec1); err != nil {
		t.Fatalf("Put v1: %v", err)
	}

	// Small sleep to ensure updated_at advances.
	time.Sleep(5 * time.Millisecond)

	rec2 := AgentSecretRecord{
		SecretID:   secretID,
		TenantID:   tenantID,
		KeyVersion: 2,
		WrappedDEK: []byte("dek-v2"),
		EncPayload: []byte("payload-v2"),
	}
	if err := s.PutAgentSecret(ctx, rec2); err != nil {
		t.Fatalf("Put v2: %v", err)
	}

	got, err := s.GetAgentSecret(ctx, tenantID, secretID)
	if err != nil {
		t.Fatalf("GetAgentSecret after overwrite: %v", err)
	}
	if string(got.WrappedDEK) != "dek-v2" {
		t.Errorf("WrappedDEK = %q; want %q", got.WrappedDEK, "dek-v2")
	}
	if string(got.EncPayload) != "payload-v2" {
		t.Errorf("EncPayload = %q; want %q", got.EncPayload, "payload-v2")
	}
	if got.KeyVersion != 2 {
		t.Errorf("KeyVersion = %d; want 2", got.KeyVersion)
	}
}

// TestPostgresAgentSecret_DeleteIdempotent verifies that deleting an absent row
// returns no error (idempotent).
func TestPostgresAgentSecret_DeleteIdempotent(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	tenantID := agentSecretTestTenant

	if err := s.DeleteAgentSecret(ctx, tenantID, "sec_never_inserted_xxxxxxxxxxx"); err != nil {
		t.Fatalf("DeleteAgentSecret (absent): %v", err)
	}
}

// TestPostgresAgentSecret_GetNotFound verifies that Get returns ErrAgentSecretNotFound
// for a non-existent row.
func TestPostgresAgentSecret_GetNotFound(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	tenantID := agentSecretTestTenant

	_, err := s.GetAgentSecret(ctx, tenantID, "sec_does_not_exist_xxxxxxxxxxxxx")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, ErrAgentSecretNotFound) {
		t.Errorf("expected ErrAgentSecretNotFound, got %v", err)
	}
}

// TestPostgresAgentSecret_RLS_CrossTenantBlocked verifies that a row inserted for
// tenantA is invisible when the GUC is set to tenantB.
//
// This test requires MINTKEY_TEST_PG_APP_DSN (mintkey_app role, no BYPASSRLS).
// Without it, the test is skipped.
func TestPostgresAgentSecret_RLS_CrossTenantBlocked(t *testing.T) {
	s := newTestPostgresStore(t)
	appPool := newAppPool(t) // skip if MINTKEY_TEST_PG_APP_DSN not set
	ctx := context.Background()

	tenantA := agentSecretTestTenant
	tenantB := "bbbbbbbb-0000-0000-0000-000000000002"
	secretID := "sec_rls_test_aaaaaaaaaaaaaaaaaaaaaa"

	cleanupAgentSecrets(t, s.pool, tenantA)
	cleanupAgentSecrets(t, s.pool, tenantB)
	t.Cleanup(func() {
		cleanupAgentSecrets(t, s.pool, tenantA)
		cleanupAgentSecrets(t, s.pool, tenantB)
	})

	// Insert a row as tenantA using the superuser store.
	rec := AgentSecretRecord{
		SecretID:   secretID,
		TenantID:   tenantA,
		KeyVersion: 1,
		WrappedDEK: []byte("rls-dek"),
		EncPayload: []byte("rls-payload"),
	}
	if err := s.PutAgentSecret(ctx, rec); err != nil {
		t.Fatalf("PutAgentSecret (tenantA): %v", err)
	}

	// Build an app-role store wrapping the appPool.
	appStore := &PostgresStore{pool: appPool}

	// GetAgentSecret as tenantA should succeed.
	_, err := appStore.GetAgentSecret(ctx, tenantA, secretID)
	if err != nil {
		t.Fatalf("GetAgentSecret (tenantA, app role): %v", err)
	}

	// GetAgentSecret as tenantB should return not-found (RLS hides the row).
	_, err = appStore.GetAgentSecret(ctx, tenantB, secretID)
	if err == nil {
		t.Fatal("expected not-found when reading tenantA row as tenantB (RLS should block)")
	}
	// The error can be ErrAgentSecretNotFound (row invisible) — that's correct.
	if !errors.Is(err, ErrAgentSecretNotFound) {
		t.Errorf("expected ErrAgentSecretNotFound from RLS block, got %v", err)
	}
}
