package config_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
)

// secretErrer is the start-up contract of Config. It is reached through this
// interface so the test compiles before SecretErr exists.
type secretErrer interface {
	SecretErr() error
}

func secretError(t *testing.T, cfg *config.Config) error {
	t.Helper()
	checker, ok := any(cfg).(secretErrer)
	if !ok {
		t.Fatal("*config.Config does not implement SecretErr")
	}
	return checker.SecretErr()
}

func writeProxySecretFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("cannot write secret file: %v", err)
	}
	return path
}

// TestLoad_ProxyTokensFromFiles_C_1c3d4087 covers the scenario "egress proxy
// tokens from files": both <NAME>_FILE variables name files holding distinct
// values and the two <NAME> variables are empty.
func TestLoad_ProxyTokensFromFiles_C_1c3d4087(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_PROXY_SERVICE_TOKEN_FILE", writeProxySecretFile(t, "proxy-from-file"))
	os.Setenv("MINTKEY_VAULT_PROXY_TOKEN_FILE", writeProxySecretFile(t, "vault-from-file"))

	cfg := config.Load()

	if cfg.ProxyServiceToken != "proxy-from-file" {
		t.Errorf("ProxyServiceToken = %q, want %q", cfg.ProxyServiceToken, "proxy-from-file")
	}
	if cfg.VaultIdentityToken != "vault-from-file" {
		t.Errorf("VaultIdentityToken = %q, want %q", cfg.VaultIdentityToken, "vault-from-file")
	}
	if err := secretError(t, cfg); err != nil {
		t.Errorf("SecretErr() = %v, want nil", err)
	}
}

// TestLoad_ProxyTokenSetTwice_C_002035f6 covers the scenario "an egress proxy
// token set twice": both forms of MINTKEY_VAULT_PROXY_TOKEN are set and
// SecretErr names both variables.
func TestLoad_ProxyTokenSetTwice_C_002035f6(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_PROXY_TOKEN", "env-secret-value")
	os.Setenv("MINTKEY_VAULT_PROXY_TOKEN_FILE", writeProxySecretFile(t, "file-secret-value"))

	cfg := config.Load()

	err := secretError(t, cfg)
	if err == nil {
		t.Fatal("SecretErr() = nil, want an error naming both forms")
	}
	msg := err.Error()
	const want = "MINTKEY_VAULT_PROXY_TOKEN and MINTKEY_VAULT_PROXY_TOKEN_FILE are both set"
	if !strings.Contains(msg, want) {
		t.Errorf("SecretErr() = %q, want it to contain %q", msg, want)
	}
	if strings.Contains(msg, "env-secret-value") || strings.Contains(msg, "file-secret-value") {
		t.Errorf("SecretErr() = %q holds a secret value", msg)
	}
}
