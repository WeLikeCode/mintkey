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

// TestLoad_SSHProxyTokenFromVariableOrFile_C_c880ceda_C_1056cd39 covers the
// scenarios "the variable alone" and "the file alone": with only
// MINTKEY_VAULT_SSH_PROXY_TOKEN set, Load("") gives VaultToken that value; with
// only MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE set, it gives the file's content.
func TestLoad_SSHProxyTokenFromVariableOrFile_C_c880ceda_C_1056cd39(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN", "from-env")

	cfg, err := Load("")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.VaultToken != "from-env" {
		t.Errorf("VaultToken = %q, want %q", cfg.VaultToken, "from-env")
	}

	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE", writeSecretFile(t, "from-file"))

	cfg, err = Load("")
	if err != nil {
		t.Fatalf("Load() with _FILE error = %v", err)
	}
	if cfg.VaultToken != "from-file" {
		t.Errorf("VaultToken = %q, want %q", cfg.VaultToken, "from-file")
	}
}

// TestLoad_SSHProxyTokenFileTrailingLineEndsRemoved_C_9703c3fc covers the
// scenario "trailing line ends are removed": a file ending in \n or \r\n gives
// the content without them; spaces and inner line ends are kept.
func TestLoad_SSHProxyTokenFileTrailingLineEndsRemoved_C_9703c3fc(t *testing.T) {
	for _, tc := range []struct {
		name    string
		content string
		want    string
	}{
		{"trailing newline", "from-file\n", "from-file"},
		{"trailing CRLF", "from-file\r\n", "from-file"},
		{"spaces kept", " from file \n\n", " from file "},
		{"inner newline kept", "line1\nline2\n", "line1\nline2"},
	} {
		os.Clearenv()
		os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE", writeSecretFile(t, tc.content))

		cfg, err := Load("")
		if err != nil {
			t.Fatalf("case %q: Load() error = %v", tc.name, err)
		}
		if cfg.VaultToken != tc.want {
			t.Errorf("case %q: VaultToken = %q, want %q", tc.name, cfg.VaultToken, tc.want)
		}
	}
}

// TestLoad_SSHProxyTokenFileWithOnlyANewline_C_de531293_C_1056cd39 covers the
// scenario "a file that holds only a newline": Load("") returns no error and
// VaultToken "". It also asserts a non-empty answer so the empty result is not
// the only thing the test can see.
func TestLoad_SSHProxyTokenFileWithOnlyANewline_C_de531293_C_1056cd39(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE", writeSecretFile(t, "\n"))

	cfg, err := Load("")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.VaultToken != "" {
		t.Errorf("VaultToken = %q, want %q", cfg.VaultToken, "")
	}

	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE", writeSecretFile(t, "from-file"))

	cfg, err = Load("")
	if err != nil {
		t.Fatalf("Load() with non-empty file error = %v", err)
	}
	if cfg.VaultToken != "from-file" {
		t.Errorf("VaultToken = %q, want %q", cfg.VaultToken, "from-file")
	}
}

// TestLoad_SSHProxyTokenSetTwice_C_aa113b10 covers the scenario "both are
// set": Load("") returns an error whose message is exactly the both-set
// message and holds neither value.
func TestLoad_SSHProxyTokenSetTwice_C_aa113b10(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN", "env-secret-value")
	os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE", writeSecretFile(t, "file-secret-value"))

	_, err := Load("")
	if err == nil {
		t.Fatal("Load() want error when both forms are set, got nil")
	}
	msg := err.Error()
	want := "MINTKEY_VAULT_SSH_PROXY_TOKEN and MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE are both set; set only one"
	if msg != want {
		t.Errorf("error message = %q, want %q", msg, want)
	}
	if strings.Contains(msg, "env-secret-value") || strings.Contains(msg, "file-secret-value") {
		t.Errorf("error message %q holds a secret value", msg)
	}
}

// TestLoad_UnreadableSSHProxyTokenFile_C_6f684b90 covers the scenario "the
// file cannot be read": the error message starts with
// MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE: cannot read and holds the path.
func TestLoad_UnreadableSSHProxyTokenFile_C_6f684b90(t *testing.T) {
	dir, err := os.MkdirTemp("", "ssh-proxy-token-*")
	if err != nil {
		t.Fatalf("cannot create temporary directory: %v", err)
	}
	if err := os.Remove(dir); err != nil {
		t.Fatalf("cannot remove temporary directory: %v", err)
	}
	path := filepath.Join(dir, "token")

	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE", path)

	_, err = Load("")
	if err == nil {
		t.Fatal("Load() want error for an unreadable token file, got nil")
	}
	msg := err.Error()
	if !strings.HasPrefix(msg, "MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE: cannot read") {
		t.Errorf("error message %q does not start with the cannot-read message", msg)
	}
	if !strings.Contains(msg, path) {
		t.Errorf("error message %q does not hold the path %q", msg, path)
	}
}
