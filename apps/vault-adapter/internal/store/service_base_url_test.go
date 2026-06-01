// service_base_url_test.go — unit tests for CredentialRecord.ServiceBaseUrl
// and the SQLite store behaviour (ServiceBaseUrl always empty on SQLite path).
//
// Phase 3 (ADR-0023): PostgresStore.Get LEFT JOINs public.services to populate
// ServiceBaseUrl. SQLite has no such JOIN, so ServiceBaseUrl stays "". These
// tests verify the struct field exists, defaults to empty on SQLite, and does
// not affect any existing round-trip behaviour.
//
// Live-postgres coverage for the JOIN is in postgres_test.go (build tag: postgres).
package store

import (
	"context"
	"testing"
)

// TestCredentialRecord_ServiceBaseUrl_DefaultEmpty verifies that a freshly
// constructed CredentialRecord has ServiceBaseUrl == "" (zero value).
func TestCredentialRecord_ServiceBaseUrl_DefaultEmpty(t *testing.T) {
	rec := CredentialRecord{}
	if rec.ServiceBaseUrl != "" {
		t.Errorf("ServiceBaseUrl zero value = %q; want \"\"", rec.ServiceBaseUrl)
	}
}

// TestSQLiteGet_ServiceBaseUrl_IsEmpty verifies that SQLite's Get path leaves
// ServiceBaseUrl empty — SQLite credentials table has no JOIN to public.services.
func TestSQLiteGet_ServiceBaseUrl_IsEmpty(t *testing.T) {
	ctx := context.Background()
	s := newTestStore(t)

	rec := baseRec()
	rec.TargetAddress = "myhost:22"
	rec.SSHUser = "admin"

	ver, err := s.Put(ctx, rec)
	if err != nil {
		t.Fatalf("Put: %v", err)
	}

	got, err := s.Get(ctx, rec.TenantID, rec.ServiceID, ver)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if got == nil {
		t.Fatal("Get returned nil")
	}

	// SQLite path never populates ServiceBaseUrl — no public.services table.
	if got.ServiceBaseUrl != "" {
		t.Errorf("SQLite Get: ServiceBaseUrl = %q; want \"\" (no JOIN on SQLite)", got.ServiceBaseUrl)
	}

	// Existing fields must be preserved unchanged.
	if got.TargetAddress != rec.TargetAddress {
		t.Errorf("TargetAddress = %q; want %q", got.TargetAddress, rec.TargetAddress)
	}
	if got.SSHUser != rec.SSHUser {
		t.Errorf("SSHUser = %q; want %q", got.SSHUser, rec.SSHUser)
	}
}

// TestCredentialRecord_ServiceBaseUrl_SetAndRead verifies that the ServiceBaseUrl
// field can be set and read back on a CredentialRecord value (struct level).
func TestCredentialRecord_ServiceBaseUrl_SetAndRead(t *testing.T) {
	rec := CredentialRecord{
		CredentialID:   "cred_abc",
		TenantID:       "t1",
		ServiceID:      "s1",
		ServiceBaseUrl: "ssh://bastion.example.com:2222",
	}
	if rec.ServiceBaseUrl != "ssh://bastion.example.com:2222" {
		t.Errorf("ServiceBaseUrl = %q; want %q", rec.ServiceBaseUrl, "ssh://bastion.example.com:2222")
	}
}
