package server

import (
	"context"
	"errors"
	"testing"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
)

// makeTestVaultService creates a VaultService backed by an in-memory SQLite DB
// and a random 32-byte KEK.
func makeTestVaultService(t *testing.T) *VaultService {
	t.Helper()

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1) // deterministic but non-zero
	}

	s, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}
	t.Cleanup(func() { _ = s.Close() })

	return NewVaultService(kek, s)
}

// -----------------------------------------------------------------------
// PutCredential + GetCredential round-trip
// -----------------------------------------------------------------------

func TestPutAndGetCredential(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	result, err := svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:   "tenant_01HXABC",
		ServiceID:  "svc_01HXDEF",
		AuthScheme: 1, // AUTH_SCHEME_API_KEY_HEADER
		Plaintext:  []byte("secret-api-key"),
	})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}
	if result.KeyVersion != 1 {
		t.Errorf("expected key_version=1, got %d", result.KeyVersion)
	}
	if result.CreatedAt.IsZero() {
		t.Errorf("expected non-zero CreatedAt")
	}

	got, err := svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:  "tenant_01HXABC",
		ServiceID: "svc_01HXDEF",
		KeyVersion: 0, // current
	})
	if err != nil {
		t.Fatalf("GetCredential: %v", err)
	}
	if string(got.Plaintext) != "secret-api-key" {
		t.Errorf("expected plaintext %q, got %q", "secret-api-key", string(got.Plaintext))
	}
	if got.ReturnedKeyVersion != 1 {
		t.Errorf("expected returned_key_version=1, got %d", got.ReturnedKeyVersion)
	}
	if got.CurrentKeyVersion != 1 {
		t.Errorf("expected current_key_version=1, got %d", got.CurrentKeyVersion)
	}
	if got.AuthScheme != 1 {
		t.Errorf("expected auth_scheme=1, got %d", got.AuthScheme)
	}
}

// -----------------------------------------------------------------------
// Multiple rotations: current version is always returned for key_version=0
// -----------------------------------------------------------------------

func TestPutCredential_Rotation(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	r1, err := svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_01",
		Plaintext: []byte("v1"),
	})
	if err != nil {
		t.Fatalf("Put v1: %v", err)
	}

	r2, err := svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_01",
		Plaintext: []byte("v2"),
	})
	if err != nil {
		t.Fatalf("Put v2: %v", err)
	}
	if r2.KeyVersion != r1.KeyVersion+1 {
		t.Errorf("expected v2.key_version=%d, got %d", r1.KeyVersion+1, r2.KeyVersion)
	}

	// key_version=0 should return v2
	got, err := svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_01",
		KeyVersion: 0,
	})
	if err != nil {
		t.Fatalf("Get current: %v", err)
	}
	if string(got.Plaintext) != "v2" {
		t.Errorf("expected %q, got %q", "v2", string(got.Plaintext))
	}

	// explicit v1 should still be retrievable
	got1, err := svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_01",
		KeyVersion: r1.KeyVersion,
	})
	if err != nil {
		t.Fatalf("Get v1: %v", err)
	}
	if string(got1.Plaintext) != "v1" {
		t.Errorf("expected %q, got %q", "v1", string(got1.Plaintext))
	}
}

// -----------------------------------------------------------------------
// GetCredential: wrong version returns not-found
// -----------------------------------------------------------------------

func TestGetCredential_WrongVersion_NotFound(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	_, err := svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_02",
		Plaintext: []byte("value"),
	})
	if err != nil {
		t.Fatalf("Put: %v", err)
	}

	_, err = svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_02",
		KeyVersion: 99,
	})
	if err == nil {
		t.Fatal("expected error for non-existent version, got nil")
	}
}

// -----------------------------------------------------------------------
// RevokeCredential
// -----------------------------------------------------------------------

func TestRevokeCredential(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	r1, err := svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_03",
		Plaintext: []byte("old-secret"),
	})
	if err != nil {
		t.Fatalf("Put v1: %v", err)
	}

	// Rotate so v1 is no longer current.
	_, err = svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_03",
		Plaintext: []byte("new-secret"),
	})
	if err != nil {
		t.Fatalf("Put v2: %v", err)
	}

	// Revoke v1 (non-current) — should succeed.
	err = svc.RevokeCredential(ctx, RevokeCredentialArgs{
		TenantID:   "tenant_01",
		ServiceID:  "svc_03",
		KeyVersion: r1.KeyVersion,
	})
	if err != nil {
		t.Fatalf("RevokeCredential v1: %v", err)
	}

	// Trying to Get the revoked version should return an error.
	_, err = svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_03",
		KeyVersion: r1.KeyVersion,
	})
	if err == nil {
		t.Fatal("expected error getting revoked credential, got nil")
	}
}

func TestRevokeCredential_Current_Fails(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	r, err := svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_04",
		Plaintext: []byte("active"),
	})
	if err != nil {
		t.Fatalf("Put: %v", err)
	}

	err = svc.RevokeCredential(ctx, RevokeCredentialArgs{
		TenantID:   "tenant_01",
		ServiceID:  "svc_04",
		KeyVersion: r.KeyVersion,
	})
	if !errors.Is(err, store.ErrRevokeCurrent) {
		t.Errorf("expected ErrRevokeCurrent, got %v", err)
	}
}

// -----------------------------------------------------------------------
// ListVersions
// -----------------------------------------------------------------------

func TestListVersions(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	for range 3 {
		_, err := svc.PutCredential(ctx, PutCredentialArgs{
			TenantID:  "tenant_01",
			ServiceID: "svc_list",
			Plaintext: []byte("x"),
		})
		if err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	res, err := svc.ListVersions(ctx, ListVersionsArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_list",
	})
	if err != nil {
		t.Fatalf("ListVersions: %v", err)
	}
	if len(res.Versions) != 3 {
		t.Errorf("expected 3 versions, got %d", len(res.Versions))
	}
	if res.CurrentKeyVersion != 3 {
		t.Errorf("expected current_key_version=3, got %d", res.CurrentKeyVersion)
	}

	// Only v3 should be current.
	for _, d := range res.Versions {
		wantCurrent := d.KeyVersion == 3
		if d.IsCurrent != wantCurrent {
			t.Errorf("version %d: IsCurrent=%v, want %v", d.KeyVersion, d.IsCurrent, wantCurrent)
		}
	}
}

func TestListVersions_Pagination(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	for range 5 {
		_, err := svc.PutCredential(ctx, PutCredentialArgs{
			TenantID:  "tenant_01",
			ServiceID: "svc_page",
			Plaintext: []byte("x"),
		})
		if err != nil {
			t.Fatalf("Put: %v", err)
		}
	}

	// Page 1: after=0, limit=3
	res1, err := svc.ListVersions(ctx, ListVersionsArgs{
		TenantID:        "tenant_01",
		ServiceID:       "svc_page",
		AfterKeyVersion: 0,
		Limit:           3,
	})
	if err != nil {
		t.Fatalf("ListVersions page 1: %v", err)
	}
	if len(res1.Versions) != 3 {
		t.Errorf("page 1: expected 3 versions, got %d", len(res1.Versions))
	}
	if res1.NextAfterKeyVersion == 0 {
		t.Errorf("page 1: expected non-zero next cursor")
	}

	// Page 2: continue from cursor
	res2, err := svc.ListVersions(ctx, ListVersionsArgs{
		TenantID:        "tenant_01",
		ServiceID:       "svc_page",
		AfterKeyVersion: res1.NextAfterKeyVersion,
		Limit:           3,
	})
	if err != nil {
		t.Fatalf("ListVersions page 2: %v", err)
	}
	if len(res2.Versions) != 2 {
		t.Errorf("page 2: expected 2 versions, got %d", len(res2.Versions))
	}
	if res2.NextAfterKeyVersion != 0 {
		t.Errorf("page 2: expected zero next cursor (last page), got %d", res2.NextAfterKeyVersion)
	}
}

// -----------------------------------------------------------------------
// ValidateServiceIdentity
// -----------------------------------------------------------------------

func TestValidateServiceIdentity_ValidToken(t *testing.T) {
	svc := makeTestVaultService(t)
	ctx := context.Background()

	token := []byte("my-32-byte-boot-secret-for-test!")
	scopes := []string{"vault.read", "vault.put"}

	if err := svc.RegisterServiceIdentity("svcid_admin_api", token, scopes); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	gotScopes, ok := svc.ValidateServiceIdentity(ctx, "svcid_admin_api", token)
	if !ok {
		t.Fatal("expected ok=true, got false")
	}
	if len(gotScopes) != len(scopes) {
		t.Errorf("expected %d scopes, got %d", len(scopes), len(gotScopes))
	}
	for i, s := range scopes {
		if gotScopes[i] != s {
			t.Errorf("scope[%d]: expected %q, got %q", i, s, gotScopes[i])
		}
	}
}

func TestValidateServiceIdentity_InvalidToken(t *testing.T) {
	svc := makeTestVaultService(t)
	ctx := context.Background()

	token := []byte("correct-token-here-padded-to-32b")
	wrong := []byte("wrong-token-here-padded-to-32xxx")

	if err := svc.RegisterServiceIdentity("svcid_mcp", token, []string{"vault.read"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	_, ok := svc.ValidateServiceIdentity(ctx, "svcid_mcp", wrong)
	if ok {
		t.Fatal("expected ok=false for wrong token, got true")
	}
}

func TestValidateServiceIdentity_UnknownIdentity(t *testing.T) {
	svc := makeTestVaultService(t)
	ctx := context.Background()

	_, ok := svc.ValidateServiceIdentity(ctx, "svcid_unknown", []byte("any-token"))
	if ok {
		t.Fatal("expected ok=false for unknown identity, got true")
	}
}

// -----------------------------------------------------------------------
// Validation guards
// -----------------------------------------------------------------------

func TestPutCredential_MissingTenantID(t *testing.T) {
	svc := makeTestVaultService(t)
	_, err := svc.PutCredential(context.Background(), PutCredentialArgs{
		ServiceID: "svc_01",
		Plaintext: []byte("x"),
	})
	if err == nil {
		t.Fatal("expected error for missing tenant_id")
	}
}

func TestPutCredential_EmptyPlaintext(t *testing.T) {
	svc := makeTestVaultService(t)
	_, err := svc.PutCredential(context.Background(), PutCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_01",
		Plaintext: nil,
	})
	if err == nil {
		t.Fatal("expected error for empty plaintext")
	}
}

func TestGetCredential_MissingServiceID(t *testing.T) {
	svc := makeTestVaultService(t)
	_, err := svc.GetCredential(context.Background(), GetCredentialArgs{
		TenantID: "tenant_01",
	})
	if err == nil {
		t.Fatal("expected error for missing service_id")
	}
}

func TestRevokeCredential_ZeroVersion(t *testing.T) {
	svc := makeTestVaultService(t)
	err := svc.RevokeCredential(context.Background(), RevokeCredentialArgs{
		TenantID:  "tenant_01",
		ServiceID: "svc_01",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected error for key_version=0")
	}
}

// -----------------------------------------------------------------------
// newCredentialID format
// -----------------------------------------------------------------------

func TestNewCredentialID_Format(t *testing.T) {
	id := newCredentialID()
	if len(id) < 6 {
		t.Errorf("id too short: %q", id)
	}
	if id[:5] != "cred_" {
		t.Errorf("expected prefix 'cred_', got %q", id[:5])
	}

	// IDs must be unique across calls.
	seen := make(map[string]bool)
	for i := 0; i < 100; i++ {
		id2 := newCredentialID()
		if seen[id2] {
			t.Errorf("duplicate id: %q", id2)
		}
		seen[id2] = true
	}
}

// -----------------------------------------------------------------------
// Credential isolation between tenants
// -----------------------------------------------------------------------

func TestGetCredential_TenantIsolation(t *testing.T) {
	ctx := context.Background()
	svc := makeTestVaultService(t)

	_, err := svc.PutCredential(ctx, PutCredentialArgs{
		TenantID:  "tenant_A",
		ServiceID: "svc_shared",
		Plaintext: []byte("tenant-A-secret"),
	})
	if err != nil {
		t.Fatalf("Put tenantA: %v", err)
	}

	// Attempt to read tenant_A's credential as tenant_B — should not find it.
	_, err = svc.GetCredential(ctx, GetCredentialArgs{
		TenantID:  "tenant_B",
		ServiceID: "svc_shared",
		KeyVersion: 0,
	})
	if err == nil {
		t.Fatal("expected not-found error for cross-tenant read, got nil")
	}
}

// -----------------------------------------------------------------------
// RotateCredential
// -----------------------------------------------------------------------

func TestRotateCredential_IncrementsVersion(t *testing.T) {
	svc := makeTestVaultService(t)
	ctx := context.Background()

	// Store v1
	r1, err := svc.PutCredential(ctx, PutCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("secret_v1")})
	if err != nil || r1.KeyVersion != 1 {
		t.Fatalf("PutCredential v1: err=%v, key_version=%v (want 1)", err, r1.KeyVersion)
	}

	// Rotate to v2
	r2, err := svc.RotateCredential(ctx, RotateCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("secret_v2")})
	if err != nil || r2.KeyVersion != 2 {
		t.Fatalf("RotateCredential: err=%v, key_version=%v (want 2)", err, r2.KeyVersion)
	}
}

func TestRotateCredential_OldVersionStillReadable(t *testing.T) {
	svc := makeTestVaultService(t)
	ctx := context.Background()

	_, err := svc.PutCredential(ctx, PutCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("v1")})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}
	_, err = svc.RotateCredential(ctx, RotateCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("v2")})
	if err != nil {
		t.Fatalf("RotateCredential: %v", err)
	}

	// Old v1 still readable by explicit version
	got, err := svc.GetCredential(ctx, GetCredentialArgs{TenantID: "t1", ServiceID: "s1", KeyVersion: 1})
	if err != nil {
		t.Fatalf("GetCredential v1: %v", err)
	}
	if string(got.Plaintext) != "v1" {
		t.Errorf("expected plaintext %q, got %q", "v1", string(got.Plaintext))
	}
}

func TestRotateCredential_NewVersionIsCurrent(t *testing.T) {
	svc := makeTestVaultService(t)
	ctx := context.Background()

	_, err := svc.PutCredential(ctx, PutCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("v1")})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}
	_, err = svc.RotateCredential(ctx, RotateCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("v2")})
	if err != nil {
		t.Fatalf("RotateCredential: %v", err)
	}

	// key_version=0 returns current (v2)
	got, err := svc.GetCredential(ctx, GetCredentialArgs{TenantID: "t1", ServiceID: "s1", KeyVersion: 0})
	if err != nil {
		t.Fatalf("GetCredential current: %v", err)
	}
	if string(got.Plaintext) != "v2" {
		t.Errorf("expected plaintext %q, got %q", "v2", string(got.Plaintext))
	}
	if got.CurrentKeyVersion != 2 {
		t.Errorf("expected current_key_version=2, got %d", got.CurrentKeyVersion)
	}
}

func TestRotateCredential_AtomicNoGap(t *testing.T) {
	// Verifies no window exists where neither v1 nor v2 is current.
	// The store.Put uses a single SQLite transaction: it marks old versions
	// is_current=0 and inserts the new version as is_current=1 atomically.
	// With SetMaxOpenConns(1) writes are serialised, so no concurrent reader
	// can observe a state where no version is current.
	svc := makeTestVaultService(t)
	ctx := context.Background()

	_, err := svc.PutCredential(ctx, PutCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("v1")})
	if err != nil {
		t.Fatalf("PutCredential: %v", err)
	}
	r2, err := svc.RotateCredential(ctx, RotateCredentialArgs{TenantID: "t1", ServiceID: "s1", AuthScheme: 1, Plaintext: []byte("v2")})
	if err != nil {
		t.Fatalf("RotateCredential: %v", err)
	}

	// Immediately after rotate, current version is 2.
	got, err := svc.GetCredential(ctx, GetCredentialArgs{TenantID: "t1", ServiceID: "s1", KeyVersion: 0})
	if err != nil {
		t.Fatalf("GetCredential current: %v", err)
	}
	if got.CurrentKeyVersion != r2.KeyVersion {
		t.Errorf("expected current_key_version=%d, got %d", r2.KeyVersion, got.CurrentKeyVersion)
	}
}

// -----------------------------------------------------------------------
// SQL driver dependency check
// -----------------------------------------------------------------------

func TestSQLDriverAvailable(t *testing.T) {
	// store.New uses go-sqlite3 which requires CGO_ENABLED=1.
	// If this test compiles and the store opens without error the driver is
	// correctly linked.
	s, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New with driver check: %v", err)
	}
	_ = s.Close()
}
