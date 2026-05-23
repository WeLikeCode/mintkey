package store

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"
)

// newTestStore creates a Store backed by a temporary SQLite file.
// The file is removed when the test ends.
func newTestStore(t *testing.T) *Store {
	t.Helper()

	f, err := os.CreateTemp(t.TempDir(), "vault-*.db")
	if err != nil {
		t.Fatalf("create temp file: %v", err)
	}
	f.Close()

	s, err := New(f.Name())
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	t.Cleanup(func() { _ = s.Close() })
	return s
}

// baseRec returns a minimal CredentialRecord for (tenantA, svcA).
func baseRec() CredentialRecord {
	return CredentialRecord{
		CredentialID: "cred_test01",
		TenantID:     "tenant_T1",
		ServiceID:    "svc_S1",
		AuthScheme:   1,
		WrappedDEK:   []byte("wrappeddek"),
		EncPayload:   []byte("encpayload"),
	}
}

func TestPutGet(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
	ver, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put: %v", err)
	}
	if ver != 1 {
		t.Errorf("first Put returned version %d; want 1", ver)
	}

	got, err := s.Get(ctx, rec.TenantID, rec.ServiceID, ver)
	if err != nil {
		t.Fatalf("Get: %v", err)
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
}

func TestGetCurrentVersion(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
	ver1, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 1: %v", err)
	}

	rec.CredentialID = "cred_test02"
	ver2, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 2: %v", err)
	}

	// key_version=0 should return the current (version 2).
	got, err := s.Get(ctx, rec.TenantID, rec.ServiceID, 0)
	if err != nil {
		t.Fatalf("Get current: %v", err)
	}
	if got.KeyVersion != ver2 {
		t.Errorf("Get(0) returned version %d; want %d (current)", got.KeyVersion, ver2)
	}
	_ = ver1
}

func TestGetWrongVersion(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
	if _, err := s.Put(ctx, rec); err != nil {
		t.Fatalf("Put: %v", err)
	}

	_, err := s.Get(ctx, rec.TenantID, rec.ServiceID, 99)
	if err == nil {
		t.Fatal("Get non-existent version should return error")
	}
	if !errors.Is(err, sql.ErrNoRows) {
		t.Errorf("expected sql.ErrNoRows in error chain; got %v", err)
	}
}

func TestPutIncrements(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
	ver1, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 1: %v", err)
	}
	rec.CredentialID = "cred_test02"
	ver2, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 2: %v", err)
	}

	if ver1 != 1 {
		t.Errorf("first version = %d; want 1", ver1)
	}
	if ver2 != 2 {
		t.Errorf("second version = %d; want 2", ver2)
	}

	// Version 2 should be current; version 1 should not.
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
		t.Error("version 1 should no longer be current after second Put")
	}
}

func TestRevoke(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
	ver1, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put 1: %v", err)
	}
	rec.CredentialID = "cred_test02"
	if _, err = s.Put(ctx, rec); err != nil {
		t.Fatalf("Put 2: %v", err)
	}

	// Revoke the non-current version 1.
	if err = s.Revoke(ctx, rec.TenantID, rec.ServiceID, ver1); err != nil {
		t.Fatalf("Revoke: %v", err)
	}

	got, err := s.Get(ctx, rec.TenantID, rec.ServiceID, ver1)
	if err != nil {
		t.Fatalf("Get after revoke: %v", err)
	}
	if !got.IsRevoked {
		t.Error("revoked version should have IsRevoked=true")
	}
}

func TestRevokeCurrentFails(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
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

func TestListVersions(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
	for i := 0; i < 3; i++ {
		rec.CredentialID = "cred_test0" + string(rune('1'+i))
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

	// Metadata only — WrappedDEK and EncPayload must be empty.
	for _, v := range versions {
		if len(v.WrappedDEK) != 0 {
			t.Errorf("version %d: WrappedDEK should be empty in listing, got %d bytes", v.KeyVersion, len(v.WrappedDEK))
		}
		if len(v.EncPayload) != 0 {
			t.Errorf("version %d: EncPayload should be empty in listing, got %d bytes", v.KeyVersion, len(v.EncPayload))
		}
	}
}
