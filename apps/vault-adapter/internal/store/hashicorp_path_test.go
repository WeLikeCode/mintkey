// Unit tests for pure doc/path helper functions in hashicorp_doc.go.
// No build tags — runs without any Vault client or network.
package store

import (
	"bytes"
	"testing"
)

func TestHashiCorpDoc_DataPath(t *testing.T) {
	got := dataPath("mintkey", "t1", "s1", 3)
	want := "mintkey/t1/s1/v3"
	if got != want {
		t.Errorf("dataPath: got %q, want %q", got, want)
	}
}

func TestHashiCorpDoc_IndexPath(t *testing.T) {
	got := indexPath("mintkey", "t1", "s1")
	want := "mintkey/t1/s1/_index"
	if got != want {
		t.Errorf("indexPath: got %q, want %q", got, want)
	}
}

func TestHashiCorpDoc_VersionDocRoundTrip(t *testing.T) {
	original := CredentialRecord{
		CredentialID:  "cred_01HABCDEF",
		TenantID:      "t1",
		ServiceID:     "s1",
		KeyVersion:    7,
		AuthScheme:    2,
		WrappedDEK:    []byte{1, 2, 3, 4},
		EncPayload:    []byte{5, 6, 7, 8},
		IsCurrent:     true,
		IsRevoked:     false,
		CreatedAt:     1716900000000000000,
		TargetURL:     "https://api.example.com",
		HeaderName:    "X-API-Key",
		QueryParam:    "api_key",
		TargetAddress: "host:22",
		SSHUser:       "admin",
	}

	m, err := marshalVersionDoc(original)
	if err != nil {
		t.Fatalf("marshalVersionDoc: %v", err)
	}

	got, err := unmarshalVersionDoc(m)
	if err != nil {
		t.Fatalf("unmarshalVersionDoc: %v", err)
	}

	if !bytes.Equal(got.WrappedDEK, original.WrappedDEK) {
		t.Errorf("WrappedDEK: got %v, want %v", got.WrappedDEK, original.WrappedDEK)
	}
	if !bytes.Equal(got.EncPayload, original.EncPayload) {
		t.Errorf("EncPayload: got %v, want %v", got.EncPayload, original.EncPayload)
	}
	if got.KeyVersion != original.KeyVersion {
		t.Errorf("KeyVersion: got %d, want %d", got.KeyVersion, original.KeyVersion)
	}
	if got.AuthScheme != original.AuthScheme {
		t.Errorf("AuthScheme: got %d, want %d", got.AuthScheme, original.AuthScheme)
	}
	if got.IsCurrent != original.IsCurrent {
		t.Errorf("IsCurrent: got %v, want %v", got.IsCurrent, original.IsCurrent)
	}
	if got.IsRevoked != original.IsRevoked {
		t.Errorf("IsRevoked: got %v, want %v", got.IsRevoked, original.IsRevoked)
	}
	if got.CreatedAt != original.CreatedAt {
		t.Errorf("CreatedAt: got %d, want %d", got.CreatedAt, original.CreatedAt)
	}
	if got.TargetURL != original.TargetURL {
		t.Errorf("TargetURL: got %q, want %q", got.TargetURL, original.TargetURL)
	}
	if got.HeaderName != original.HeaderName {
		t.Errorf("HeaderName: got %q, want %q", got.HeaderName, original.HeaderName)
	}
	if got.QueryParam != original.QueryParam {
		t.Errorf("QueryParam: got %q, want %q", got.QueryParam, original.QueryParam)
	}
	if got.TargetAddress != original.TargetAddress {
		t.Errorf("TargetAddress: got %q, want %q", got.TargetAddress, original.TargetAddress)
	}
	if got.SSHUser != original.SSHUser {
		t.Errorf("SSHUser: got %q, want %q", got.SSHUser, original.SSHUser)
	}
}

func TestHashiCorpDoc_LimitClamp(t *testing.T) {
	cases := []struct {
		in   uint32
		want uint32
	}{
		{0, 50},
		{201, 50},
		{10, 10},
		{200, 200},
		{1, 1},
		{50, 50},
	}
	for _, tc := range cases {
		got := clampLimit(tc.in)
		if got != tc.want {
			t.Errorf("clampLimit(%d): got %d, want %d", tc.in, got, tc.want)
		}
	}
}

func TestHashiCorpDoc_IndexRoundTrip(t *testing.T) {
	original := versionIndex{Current: 3, Max: 3, Versions: []uint32{1, 2, 3}}

	m := marshalIndex(original)
	got, err := unmarshalIndex(m)
	if err != nil {
		t.Fatalf("unmarshalIndex: %v", err)
	}

	if got.Current != original.Current {
		t.Errorf("Current: got %d, want %d", got.Current, original.Current)
	}
	if got.Max != original.Max {
		t.Errorf("Max: got %d, want %d", got.Max, original.Max)
	}
	if len(got.Versions) != len(original.Versions) {
		t.Fatalf("Versions len: got %d, want %d", len(got.Versions), len(original.Versions))
	}
	for i, v := range original.Versions {
		if got.Versions[i] != v {
			t.Errorf("Versions[%d]: got %d, want %d", i, got.Versions[i], v)
		}
	}
}
