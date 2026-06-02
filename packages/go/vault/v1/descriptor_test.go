package vaultv1_test

import (
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

// enumDesc returns the AuthScheme enum descriptor from the embedded FileDescriptorProto.
// This is shared by both test functions below.
func authSchemeEnumDesc(t *testing.T) protoreflect.EnumDescriptor {
	t.Helper()
	var msg proto.Message = &vaultv1.GetCredentialResponse{}
	fd := msg.ProtoReflect().Descriptor().ParentFile()
	enumDesc := fd.Enums().ByName("AuthScheme")
	if enumDesc == nil {
		t.Fatal("AuthScheme enum not found in file descriptor")
	}
	return enumDesc
}

// TestAuthSchemeDescriptorHasValue8 asserts that the FileDescriptorProto
// embedded in vault.pb.go knows about AUTH_SCHEME_OAUTH2_PASSWORD_GRANT (8).
// This catches the hand-edit bug where the rawDesc bytes were not regenerated:
// the int32 constant was present but the descriptor name mapping was absent,
// making protoreflect.ByNumber(8).Name() return "" and protoreflect.ByName() nil.
func TestAuthSchemeDescriptorHasValue8(t *testing.T) {
	enumDesc := authSchemeEnumDesc(t)

	const (
		wantNumber = protoreflect.EnumNumber(8)
		wantName   = protoreflect.Name("AUTH_SCHEME_OAUTH2_PASSWORD_GRANT")
	)

	// ByNumber: descriptor must return the correct name
	byNum := enumDesc.Values().ByNumber(wantNumber)
	if byNum == nil {
		t.Fatalf("Values().ByNumber(8) returned nil — descriptor does not know value 8")
	}
	if byNum.Name() != wantName {
		t.Errorf("Values().ByNumber(8).Name() = %q; want %q", byNum.Name(), wantName)
	}

	// ByName: descriptor must return the correct number
	byName := enumDesc.Values().ByName(wantName)
	if byName == nil {
		t.Fatalf("Values().ByName(%q) returned nil — descriptor does not know the name", wantName)
	}
	if byName.Number() != wantNumber {
		t.Errorf("Values().ByName(%q).Number() = %d; want %d", wantName, byName.Number(), wantNumber)
	}
}

// TestAuthSchemeReflection asserts that the binary descriptor in vault.pb.go
// (file_vault_proto_rawDesc) knows about the three email enum values added in C-2
// (14 = EMAIL_PASSWORD, 15 = EMAIL_OAUTH2, 16 = EMAIL_APP_PASSWORD).
//
// A hand-patched pb.go can have correct int32 constants + name/value maps but a
// stale rawDesc — causing AuthScheme(14).String() to return "14" instead of
// "AUTH_SCHEME_EMAIL_PASSWORD" and Descriptor().Values().ByNumber(14) to return nil.
// This test catches both failure modes.
func TestAuthSchemeReflection(t *testing.T) {
	enumDesc := authSchemeEnumDesc(t)

	cases := []struct {
		v    vaultv1.AuthScheme
		name string
	}{
		{vaultv1.AuthScheme_AUTH_SCHEME_EMAIL_PASSWORD, "AUTH_SCHEME_EMAIL_PASSWORD"},
		{vaultv1.AuthScheme_AUTH_SCHEME_EMAIL_OAUTH2, "AUTH_SCHEME_EMAIL_OAUTH2"},
		{vaultv1.AuthScheme_AUTH_SCHEME_EMAIL_APP_PASSWORD, "AUTH_SCHEME_EMAIL_APP_PASSWORD"},
	}

	for _, c := range cases {
		// 1. String() must return the canonical name, not a decimal number.
		if got := c.v.String(); got != c.name {
			t.Errorf("AuthScheme(%d).String() = %q, want %q", c.v, got, c.name)
		}

		// 2. Descriptor().Values().ByNumber must find the value.
		n := protoreflect.EnumNumber(c.v)
		byNum := enumDesc.Values().ByNumber(n)
		if byNum == nil {
			t.Fatalf("Descriptor().Values().ByNumber(%d) returned nil — rawDesc not regenerated", n)
		}
		if string(byNum.Name()) != c.name {
			t.Errorf("ByNumber(%d).Name() = %q, want %q", n, byNum.Name(), c.name)
		}

		// 3. Descriptor().Values().ByName must find the value.
		byName := enumDesc.Values().ByName(protoreflect.Name(c.name))
		if byName == nil {
			t.Fatalf("Descriptor().Values().ByName(%q) returned nil", c.name)
		}
		if byName.Number() != n {
			t.Errorf("ByName(%q).Number() = %d, want %d", c.name, byName.Number(), n)
		}
	}
}
