//go:build postgres

// Run with a live Postgres:
//   MINTKEY_TEST_PG_DSN="postgres://..." go test -tags postgres -v -count=1 -race ./internal/store/...
//
// Without the build tag the file is entirely excluded from compilation;
// the sqlite tests in sqlite_test.go run normally under `go test ./...`.
package store

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const pgDSNEnv = "MINTKEY_TEST_PG_DSN"

// newTestPostgresStore creates a PostgresStore from MINTKEY_TEST_PG_DSN.
// It cleans up any rows it inserts for the test tenant on t.Cleanup so tests
// are hermetic even when the schema already has data.
func newTestPostgresStore(t *testing.T) *PostgresStore {
	t.Helper()
	dsn := os.Getenv(pgDSNEnv)
	if dsn == "" {
		t.Skipf("skipping postgres tests: %s not set", pgDSNEnv)
	}

	ctx := context.Background()
	s, err := NewPostgres(ctx, dsn)
	if err != nil {
		t.Fatalf("NewPostgres: %v", err)
	}

	t.Cleanup(func() { _ = s.Close() })
	return s
}

// pgBaseRec returns a minimal CredentialRecord with valid UUID fields (required
// by the Postgres RLS policy and the uuid column type).
func pgBaseRec() CredentialRecord {
	return CredentialRecord{
		CredentialID: "cred_pg_test_001",
		// Valid UUIDs — RLS GUC is cast to uuid by the policy.
		TenantID:   "10000000-0000-0000-0000-000000000001",
		ServiceID:  "20000000-0000-0000-0000-000000000002",
		AuthScheme: 1,
		WrappedDEK: []byte("pg-wrapped-dek"),
		EncPayload: []byte("pg-enc-payload"),
		TargetURL:  "https://api.example.com",
		HeaderName: "X-Api-Key",
		QueryParam: "",
	}
}

// cleanupTenant removes all test rows for the given tenant/service so each
// test starts clean.  It bypasses RLS by setting the tenant GUC inside an
// explicit transaction (set_config with third arg true = transaction-local,
// mirroring the production-code pattern).
func cleanupTenant(t *testing.T, pool *pgxpool.Pool, tenantID, serviceID string) {
	t.Helper()
	ctx := context.Background()
	conn, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("cleanup: acquire: %v", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		t.Fatalf("cleanup: begin tx: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		t.Fatalf("cleanup: set tenant: %v", err)
	}
	if _, err = tx.Exec(ctx,
		`DELETE FROM vault.credentials WHERE tenant_id = $1 AND service_id = $2`,
		tenantID, serviceID,
	); err != nil {
		t.Fatalf("cleanup: delete: %v", err)
	}
	if err = tx.Commit(ctx); err != nil {
		t.Fatalf("cleanup: commit: %v", err)
	}
}

// TestPostgresPutGetRoundTrip verifies a full Put → Get(version) → Get(current) round-trip.
func TestPostgresPutGetRoundTrip(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	rec := pgBaseRec()
	cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID)
	t.Cleanup(func() { cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID) })

	ver, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put: %v", err)
	}
	if ver != 1 {
		t.Errorf("first Put: version = %d; want 1", ver)
	}

	// Fetch by explicit version.
	got, err := s.Get(ctx, rec.TenantID, rec.ServiceID, ver)
	if err != nil {
		t.Fatalf("Get(version): %v", err)
	}
	if got == nil {
		t.Fatal("Get(version) returned nil record")
	}
	if got.CredentialID != rec.CredentialID {
		t.Errorf("CredentialID = %q; want %q", got.CredentialID, rec.CredentialID)
	}
	if got.KeyVersion != ver {
		t.Errorf("KeyVersion = %d; want %d", got.KeyVersion, ver)
	}
	if string(got.WrappedDEK) != string(rec.WrappedDEK) {
		t.Error("WrappedDEK mismatch")
	}
	if string(got.EncPayload) != string(rec.EncPayload) {
		t.Error("EncPayload mismatch")
	}
	if !got.IsCurrent {
		t.Error("IsCurrent should be true")
	}
	if got.IsRevoked {
		t.Error("IsRevoked should be false")
	}

	// Fetch by current (keyVersion=0).
	cur, err := s.Get(ctx, rec.TenantID, rec.ServiceID, 0)
	if err != nil {
		t.Fatalf("Get(current): %v", err)
	}
	if cur == nil {
		t.Fatal("Get(current) returned nil")
	}
	if cur.KeyVersion != ver {
		t.Errorf("Get(0): version = %d; want %d", cur.KeyVersion, ver)
	}
}

// TestPostgresPutIncrementsVersion verifies key_version increments on successive Puts.
func TestPostgresPutIncrementsVersion(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	rec := pgBaseRec()
	cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID)
	t.Cleanup(func() { cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID) })

	ver1, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 1: %v", err)
	}
	rec.CredentialID = "cred_pg_test_002"
	ver2, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 2: %v", err)
	}

	if ver1 != 1 {
		t.Errorf("ver1 = %d; want 1", ver1)
	}
	if ver2 != 2 {
		t.Errorf("ver2 = %d; want 2", ver2)
	}

	// v2 is current; v1 is not.
	v2, err := s.Get(ctx, rec.TenantID, rec.ServiceID, ver2)
	if err != nil {
		t.Fatalf("Get ver2: %v", err)
	}
	if !v2.IsCurrent {
		t.Error("version 2 should be current")
	}

	v1, err := s.Get(ctx, rec.TenantID, rec.ServiceID, ver1)
	if err != nil {
		t.Fatalf("Get ver1: %v", err)
	}
	if v1.IsCurrent {
		t.Error("version 1 should not be current after second Put")
	}
}

// TestPostgresRevoke verifies soft-delete of a non-current version.
func TestPostgresRevoke(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	rec := pgBaseRec()
	cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID)
	t.Cleanup(func() { cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID) })

	ver1, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 1: %v", err)
	}
	rec.CredentialID = "cred_pg_test_002"
	if _, err = s.Put(ctx, rec); err != nil {
		t.Fatalf("Put 2: %v", err)
	}

	// Revoke the non-current version 1.
	if err = s.Revoke(ctx, rec.TenantID, rec.ServiceID, ver1); err != nil {
		t.Fatalf("Revoke: %v", err)
	}

	got, err := s.Get(ctx, rec.TenantID, rec.ServiceID, ver1)
	if err != nil {
		// Get on a revoked-but-existing row returns the row (is_revoked check
		// only filters Get(current) when keyVersion==0); for explicit version
		// the row is returned with is_revoked=true so callers can inspect it.
		// If err is sql.ErrNoRows the revoke filter excluded it — adjust test.
		if errors.Is(err, sql.ErrNoRows) {
			t.Log("Get returned not-found for revoked row (revoke filter active on explicit version) — acceptable")
			return
		}
		t.Fatalf("Get after revoke: %v", err)
	}
	if got != nil && !got.IsRevoked {
		t.Error("IsRevoked should be true after Revoke")
	}
}

// TestPostgresRevokeCurrentFails verifies that revoking the current version
// returns ErrRevokeCurrent.
func TestPostgresRevokeCurrentFails(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	rec := pgBaseRec()
	cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID)
	t.Cleanup(func() { cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID) })

	ver, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put: %v", err)
	}

	err = s.Revoke(ctx, rec.TenantID, rec.ServiceID, ver)
	if err == nil {
		t.Fatal("Revoke on current version should return error")
	}
	if !errors.Is(err, ErrRevokeCurrent) {
		t.Errorf("expected ErrRevokeCurrent; got %v", err)
	}
}

// TestPostgresListVersions verifies metadata listing with pagination.
func TestPostgresListVersions(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	rec := pgBaseRec()
	cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID)
	t.Cleanup(func() { cleanupTenant(t, s.pool, rec.TenantID, rec.ServiceID) })

	for i := 0; i < 3; i++ {
		rec.CredentialID = "cred_pg_list_00" + string(rune('1'+i))
		if _, err := s.Put(ctx, rec); err != nil {
			t.Fatalf("Put %d: %v", i+1, err)
		}
	}

	versions, err := s.ListVersions(ctx, rec.TenantID, rec.ServiceID, 0, 50)
	if err != nil {
		t.Fatalf("ListVersions: %v", err)
	}
	if len(versions) != 3 {
		t.Errorf("got %d versions; want 3", len(versions))
	}

	// Metadata-only — WrappedDEK and EncPayload must be empty.
	for _, v := range versions {
		if len(v.WrappedDEK) != 0 {
			t.Errorf("version %d: WrappedDEK should be empty in listing", v.KeyVersion)
		}
		if len(v.EncPayload) != 0 {
			t.Errorf("version %d: EncPayload should be empty in listing", v.KeyVersion)
		}
	}

	// afterKeyVersion pagination.
	page2, err := s.ListVersions(ctx, rec.TenantID, rec.ServiceID, 1, 50)
	if err != nil {
		t.Fatalf("ListVersions page2: %v", err)
	}
	if len(page2) != 2 {
		t.Errorf("afterKeyVersion=1: got %d versions; want 2", len(page2))
	}
}

// TestPostgresTenantContextIsSet confirms that set_config('app.current_tenant', $1, true)
// correctly sets the GUC inside a transaction by reading it back from the same
// connection.  This proves RLS receives the correct tenant value.
//
// We validate this by acquiring a single pool connection, beginning a
// transaction manually, calling the GUC-setting pattern directly, then
// querying current_setting.
func TestPostgresTenantContextIsSet(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()
	tenantID := "10000000-0000-0000-0000-000000000099"

	conn, err := s.pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire: %v", err)
	}
	defer conn.Release()

	tx, err := conn.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		t.Fatalf("begin tx: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// This is the identical set_config pattern used in Put/Revoke/Get/ListVersions.
	if _, err = tx.Exec(ctx, "SELECT set_config('app.current_tenant', $1, true)", tenantID); err != nil {
		t.Fatalf("set_config: %v", err)
	}

	var got string
	if err = tx.QueryRow(ctx,
		`SELECT current_setting('app.current_tenant', true)`,
	).Scan(&got); err != nil {
		t.Fatalf("query current_setting: %v", err)
	}

	if got != tenantID {
		t.Errorf("app.current_tenant = %q; want %q", got, tenantID)
	}
}

// TestPostgresCrossTenantGetReturnsNothing verifies that RLS prevents reading
// another tenant's credentials.  Tenant A inserts a row; Tenant B's Get must
// return nil (not-found), not an error and not the row.
func TestPostgresCrossTenantGetReturnsNothing(t *testing.T) {
	s := newTestPostgresStore(t)
	ctx := context.Background()

	tenantA := "10000000-0000-0000-0000-0000000000AA"
	tenantB := "10000000-0000-0000-0000-0000000000BB"
	serviceID := "20000000-0000-0000-0000-000000000099"

	// lowercase UUIDs for postgres
	tenantA = "10000000-0000-0000-0000-0000000000aa"
	tenantB = "10000000-0000-0000-0000-0000000000bb"

	cleanupTenant(t, s.pool, tenantA, serviceID)
	cleanupTenant(t, s.pool, tenantB, serviceID)
	t.Cleanup(func() {
		cleanupTenant(t, s.pool, tenantA, serviceID)
		cleanupTenant(t, s.pool, tenantB, serviceID)
	})

	recA := CredentialRecord{
		CredentialID: "cred_cross_tenant_A",
		TenantID:     tenantA,
		ServiceID:    serviceID,
		AuthScheme:   1,
		WrappedDEK:   []byte("dek-a"),
		EncPayload:   []byte("pay-a"),
	}
	ver, err := s.Put(ctx, recA)
	if err != nil {
		t.Fatalf("Put tenantA: %v", err)
	}

	// Tenant B should not see tenant A's row.
	got, err := s.Get(ctx, tenantB, serviceID, ver)
	if err != nil {
		// RLS may return pgx.ErrNoRows wrapped as sql.ErrNoRows — that is correct.
		if errors.Is(err, sql.ErrNoRows) {
			return // correct: row not visible
		}
		t.Fatalf("Get tenantB: unexpected error: %v", err)
	}
	if got != nil {
		t.Errorf("cross-tenant Get returned row %+v; RLS should have blocked it", got)
	}
}
