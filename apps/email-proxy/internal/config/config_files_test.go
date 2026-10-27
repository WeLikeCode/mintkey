package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// writeSecretFile writes content to a fresh file and returns its path, so a
// test can name it in a <NAME>_FILE variable.
func writeSecretFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("cannot write secret file: %v", err)
	}
	return path
}

// TestLoad_EmailProxyTokensFromFiles_C_5f8ede28 covers the scenario "email
// proxy tokens from files": with the two <NAME> variables empty and their
// <NAME>_FILE forms naming files, Load() returns the file contents.
func TestLoad_EmailProxyTokensFromFiles_C_5f8ede28(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN_FILE", writeSecretFile(t, "vault-file-token"))
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE", writeSecretFile(t, "svc-file-token"))

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.VaultToken != "vault-file-token" {
		t.Errorf("VaultToken = %q, want %q", cfg.VaultToken, "vault-file-token")
	}
	if cfg.EmailProxyServiceToken != "svc-file-token" {
		t.Errorf("EmailProxyServiceToken = %q, want %q", cfg.EmailProxyServiceToken, "svc-file-token")
	}
}

// TestLoad_UnreadableEmailProxyTokenFile_C_427d1fb9 covers the scenario "an
// unreadable email proxy token file": Load() returns an error whose message
// contains MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE.
func TestLoad_UnreadableEmailProxyTokenFile_C_427d1fb9(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "does-not-exist", "token")

	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE", missing)

	_, err := Load()
	if err == nil {
		t.Fatal("Load() want error for an unreadable service token file, got nil")
	}
	if !strings.Contains(err.Error(), "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE") {
		t.Errorf("error message %q does not name MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE", err.Error())
	}
}

// TestLoad_EmailProxyTokenFileWithOnlyANewline_C_75341d48_C_5f8ede28 covers
// the scenario "an email proxy token file that holds only a newline": Load()
// returns MINTKEY_VAULT_EMAIL_PROXY_TOKEN is required but not set. It also
// asserts that a non-empty token file is read, so the empty result is not the
// only thing the test can see.
func TestLoad_EmailProxyTokenFileWithOnlyANewline_C_75341d48_C_5f8ede28(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN_FILE", writeSecretFile(t, "\n"))
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_test")

	_, err := Load()
	if err == nil {
		t.Fatal("Load() want error for a vault token file holding only a newline, got nil")
	}
	want := "MINTKEY_VAULT_EMAIL_PROXY_TOKEN is required but not set"
	if err.Error() != want {
		t.Errorf("error message = %q, want %q", err.Error(), want)
	}

	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN_FILE", writeSecretFile(t, "vault-file-token"))
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_test")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() with a non-empty vault token file error = %v", err)
	}
	if cfg.VaultToken != "vault-file-token" {
		t.Errorf("VaultToken = %q, want %q", cfg.VaultToken, "vault-file-token")
	}
}
