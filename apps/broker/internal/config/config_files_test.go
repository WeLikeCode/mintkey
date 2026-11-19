package config_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/config"
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

func writeBrokerSecretFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("cannot write secret file: %v", err)
	}
	return path
}

// TestLoad_BrokerTokensFromFiles_C_d2cf4459 covers the scenario "broker tokens
// from files": each <NAME>_FILE names a file holding a distinct value and the
// four <NAME> variables are empty.
func TestLoad_BrokerTokensFromFiles_C_d2cf4459(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_SERVICE_TOKEN_FILE", writeBrokerSecretFile(t, "service-from-file"))
	os.Setenv("MINTKEY_PROXY_SERVICE_TOKEN_FILE", writeBrokerSecretFile(t, "proxy-from-file"))
	os.Setenv("MINTKEY_MCP_SERVICE_TOKEN_FILE", writeBrokerSecretFile(t, "mcp-from-file"))
	os.Setenv("MINTKEY_BROKER_SERVICE_TOKEN_FILE", writeBrokerSecretFile(t, "broker-from-file"))

	cfg := config.Load()

	if cfg.ServiceToken != "service-from-file" {
		t.Errorf("ServiceToken = %q, want %q", cfg.ServiceToken, "service-from-file")
	}
	if cfg.ProxyServiceToken != "proxy-from-file" {
		t.Errorf("ProxyServiceToken = %q, want %q", cfg.ProxyServiceToken, "proxy-from-file")
	}
	if cfg.MCPServiceToken != "mcp-from-file" {
		t.Errorf("MCPServiceToken = %q, want %q", cfg.MCPServiceToken, "mcp-from-file")
	}
	if cfg.BrokerSvcToken != "broker-from-file" {
		t.Errorf("BrokerSvcToken = %q, want %q", cfg.BrokerSvcToken, "broker-from-file")
	}
	if err := secretError(t, cfg); err != nil {
		t.Errorf("SecretErr() = %v, want nil", err)
	}
}

// TestLoad_BrokerTokensFromVariables_C_f379fedb covers the scenario "broker
// tokens from variables, as before": the four <NAME> variables hold distinct
// values and no <NAME>_FILE variable is set.
func TestLoad_BrokerTokensFromVariables_C_f379fedb(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_SERVICE_TOKEN", "service-from-env")
	os.Setenv("MINTKEY_PROXY_SERVICE_TOKEN", "proxy-from-env")
	os.Setenv("MINTKEY_MCP_SERVICE_TOKEN", "mcp-from-env")
	os.Setenv("MINTKEY_BROKER_SERVICE_TOKEN", "broker-from-env")

	cfg := config.Load()

	if cfg.ServiceToken != "service-from-env" {
		t.Errorf("ServiceToken = %q, want %q", cfg.ServiceToken, "service-from-env")
	}
	if cfg.ProxyServiceToken != "proxy-from-env" {
		t.Errorf("ProxyServiceToken = %q, want %q", cfg.ProxyServiceToken, "proxy-from-env")
	}
	if cfg.MCPServiceToken != "mcp-from-env" {
		t.Errorf("MCPServiceToken = %q, want %q", cfg.MCPServiceToken, "mcp-from-env")
	}
	if cfg.BrokerSvcToken != "broker-from-env" {
		t.Errorf("BrokerSvcToken = %q, want %q", cfg.BrokerSvcToken, "broker-from-env")
	}
	if err := secretError(t, cfg); err != nil {
		t.Errorf("SecretErr() = %v, want nil", err)
	}
}

// TestLoad_UnreadableBrokerTokenFile_C_64df9824 covers the scenario "an
// unreadable broker token file": MCPServiceToken is "" and SecretErr names the
// variable.
func TestLoad_UnreadableBrokerTokenFile_C_64df9824(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "missing-token")

	os.Clearenv()
	os.Setenv("MINTKEY_MCP_SERVICE_TOKEN_FILE", missing)

	cfg := config.Load()

	if cfg.MCPServiceToken != "" {
		t.Errorf("MCPServiceToken = %q, want %q", cfg.MCPServiceToken, "")
	}
	err := secretError(t, cfg)
	if err == nil {
		t.Fatal("SecretErr() = nil, want an error naming the unreadable file")
	}
	if !strings.Contains(err.Error(), "MINTKEY_MCP_SERVICE_TOKEN_FILE") {
		t.Errorf("SecretErr() = %q, want it to hold MINTKEY_MCP_SERVICE_TOKEN_FILE", err.Error())
	}
}
