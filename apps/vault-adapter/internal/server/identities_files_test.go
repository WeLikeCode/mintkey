package server

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// bootIdentityVars are the id and token variables of BootIdentities, without
// their _FILE forms.
var bootIdentityVars = []string{
	"MINTKEY_VAULT_PROXY_IDENTITY_ID",
	"MINTKEY_VAULT_ADMIN_IDENTITY_ID",
	"MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID",
	"MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID",
	"MINTKEY_VAULT_MCP_IDENTITY_ID",
	"MINTKEY_VAULT_PROXY_TOKEN",
	"MINTKEY_VAULT_ADMIN_TOKEN",
	"MINTKEY_VAULT_SSH_PROXY_TOKEN",
	"MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
	"MINTKEY_VAULT_MCP_TOKEN",
}

// clearBootIdentityEnv sets every boot identity id and token variable, and its
// _FILE form, to the empty string so each test starts from a known environment.
func clearBootIdentityEnv(t *testing.T) {
	t.Helper()
	for _, name := range bootIdentityVars {
		t.Setenv(name, "")
		t.Setenv(name+"_FILE", "")
	}
}

// writeIdentitySecretFile writes content to a fresh file and returns its path.
func writeIdentitySecretFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("cannot write secret file: %v", err)
	}
	return path
}

// TestRegisterBootIdentitiesFromEnv_TokenFromFile_C_5c46e7e4 covers the
// scenario "an identity token from a file": MINTKEY_VAULT_ADMIN_TOKEN_FILE
// names a file holding a 32-byte token followed by a newline, so the admin
// identity is registered with the token without the line end.
func TestRegisterBootIdentitiesFromEnv_TokenFromFile_C_5c46e7e4(t *testing.T) {
	svc := makeTestVaultService(t)
	clearBootIdentityEnv(t)

	adminToken := strings.Repeat("b", 32)
	t.Setenv("MINTKEY_VAULT_ADMIN_TOKEN_FILE", writeIdentitySecretFile(t, adminToken+"\n"))

	unset, err := svc.RegisterBootIdentitiesFromEnv("dev")
	if err != nil {
		t.Fatalf("RegisterBootIdentitiesFromEnv: %v", err)
	}
	wantUnset := []string{
		"MINTKEY_VAULT_PROXY_TOKEN",
		"MINTKEY_VAULT_SSH_PROXY_TOKEN",
		"MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
		"MINTKEY_VAULT_MCP_TOKEN",
	}
	if !reflect.DeepEqual(unset, wantUnset) {
		t.Fatalf("unset = %v, want %v", unset, wantUnset)
	}

	if _, ok := svc.ValidateServiceIdentity(context.Background(), "svcid_admin_api", []byte(adminToken)); !ok {
		t.Fatal("ValidateServiceIdentity(svcid_admin_api) refused the token read from the file")
	}
}

// TestRegisterBootIdentitiesFromEnv_UnreadableTokenFile_C_48ed3d61 covers the
// scenario "an unreadable identity token file": the error names
// MINTKEY_VAULT_PROXY_TOKEN_FILE and no identity is registered, so the admin
// token set in the environment is refused.
func TestRegisterBootIdentitiesFromEnv_UnreadableTokenFile_C_48ed3d61(t *testing.T) {
	svc := makeTestVaultService(t)
	clearBootIdentityEnv(t)

	adminToken := strings.Repeat("b", 32)
	t.Setenv("MINTKEY_VAULT_ADMIN_TOKEN", adminToken)
	t.Setenv("MINTKEY_VAULT_PROXY_TOKEN_FILE", filepath.Join(t.TempDir(), "missing-token"))

	_, err := svc.RegisterBootIdentitiesFromEnv("dev")
	if err == nil {
		t.Fatal("RegisterBootIdentitiesFromEnv = nil error, want the unreadable file error")
	}
	if !strings.Contains(err.Error(), "MINTKEY_VAULT_PROXY_TOKEN_FILE") {
		t.Fatalf("error = %q, want it to hold MINTKEY_VAULT_PROXY_TOKEN_FILE", err.Error())
	}

	if _, ok := svc.ValidateServiceIdentity(context.Background(), "svcid_admin_api", []byte(adminToken)); ok {
		t.Fatal("ValidateServiceIdentity(svcid_admin_api) accepted a token although a read failed")
	}
}
