package vaultv1_test

import (
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
)

// TestAuthSchemeDescriptorHasValue8 asserts that the FileDescriptorProto
// embedded in vault.pb.go knows about AUTH_SCHEME_OAUTH2_PASSWORD_GRANT (8).
// This catches the hand-edit bug where the rawDesc bytes were not regenerated:
// the int32 constant was present but the descriptor name mapping was absent,
// making protoreflect.ByNumber(8).Name() return "" and protoreflect.ByName() nil.
func TestAuthSchemeDescriptorHasValue8(t *testing.T) {
	var msg proto.Message = &vaultv1.GetCredentialResponse{}
	fd := msg.ProtoReflect().Descriptor().ParentFile()

	enumDesc := fd.Enums().ByName("AuthScheme")
	if enumDesc == nil {
		t.Fatal("AuthScheme enum not found in file descriptor")
	}

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
