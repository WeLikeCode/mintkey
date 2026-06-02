package config

import (
	"os"
	"testing"
)

func TestLoad_Defaults(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_test")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.BrokerJWKSURL != "http://broker:8083/.well-known/jwks.json" {
		t.Errorf("BrokerJWKSURL = %q, want default", cfg.BrokerJWKSURL)
	}
	if cfg.VaultGRPCAddr != "vault-adapter:8084" {
		t.Errorf("VaultGRPCAddr = %q, want default", cfg.VaultGRPCAddr)
	}
	if cfg.HTTPPort != 8088 {
		t.Errorf("HTTPPort = %d, want 8088", cfg.HTTPPort)
	}
	if cfg.MetricsPort != 8090 {
		t.Errorf("MetricsPort = %d, want 8090 (NOT 8087 — collides with ssh-proxy healthz)", cfg.MetricsPort)
	}
	if cfg.LogLevel != "info" {
		t.Errorf("LogLevel = %q, want info", cfg.LogLevel)
	}
	if cfg.AdminAPIInternalURL != "http://admin-api:8080" {
		t.Errorf("AdminAPIInternalURL = %q, want default", cfg.AdminAPIInternalURL)
	}
	if cfg.VaultIdentityID != "id_test" {
		t.Errorf("VaultIdentityID = %q, want id_test", cfg.VaultIdentityID)
	}
	if cfg.VaultToken != "tok_test" {
		t.Errorf("VaultToken = %q, want tok_test", cfg.VaultToken)
	}
	if cfg.EmailProxyServiceToken != "svc_tok_test" {
		t.Errorf("EmailProxyServiceToken = %q, want svc_tok_test", cfg.EmailProxyServiceToken)
	}
}

func TestLoad_MissingIdentityID(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID is missing")
	}
}

func TestLoad_MissingToken(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when MINTKEY_VAULT_EMAIL_PROXY_TOKEN is missing")
	}
}

func TestLoad_BothRequiredMissing(t *testing.T) {
	os.Clearenv()

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when both required vars are missing")
	}
}

func TestLoad_Overrides(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_prod")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_prod")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_prod")
	os.Setenv("MINTKEY_BROKER_JWKS_URL", "http://my-broker:9999/.well-known/jwks.json")
	os.Setenv("MINTKEY_VAULT_GRPC_ADDR", "my-vault:1234")
	os.Setenv("MINTKEY_EMAIL_PROXY_HTTP_PORT", "9088")
	os.Setenv("MINTKEY_EMAIL_PROXY_METRICS_PORT", "9090")
	os.Setenv("MINTKEY_EMAIL_PROXY_LOG_LEVEL", "debug")
	os.Setenv("MINTKEY_ADMIN_API_INTERNAL_URL", "http://my-admin:8888")
	os.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel:4317")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.BrokerJWKSURL != "http://my-broker:9999/.well-known/jwks.json" {
		t.Errorf("BrokerJWKSURL = %q", cfg.BrokerJWKSURL)
	}
	if cfg.VaultGRPCAddr != "my-vault:1234" {
		t.Errorf("VaultGRPCAddr = %q", cfg.VaultGRPCAddr)
	}
	if cfg.HTTPPort != 9088 {
		t.Errorf("HTTPPort = %d, want 9088", cfg.HTTPPort)
	}
	if cfg.MetricsPort != 9090 {
		t.Errorf("MetricsPort = %d, want 9090", cfg.MetricsPort)
	}
	if cfg.LogLevel != "debug" {
		t.Errorf("LogLevel = %q, want debug", cfg.LogLevel)
	}
	if cfg.AdminAPIInternalURL != "http://my-admin:8888" {
		t.Errorf("AdminAPIInternalURL = %q", cfg.AdminAPIInternalURL)
	}
	if cfg.OTelEndpoint != "otel:4317" {
		t.Errorf("OTelEndpoint = %q", cfg.OTelEndpoint)
	}
	if cfg.EmailProxyServiceToken != "svc_tok_prod" {
		t.Errorf("EmailProxyServiceToken = %q, want svc_tok_prod", cfg.EmailProxyServiceToken)
	}
}

// TestLoad_MissingServiceToken verifies MINTKEY_EMAIL_PROXY_SERVICE_TOKEN is required.
func TestLoad_MissingServiceToken(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	// MINTKEY_EMAIL_PROXY_SERVICE_TOKEN intentionally not set.

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when MINTKEY_EMAIL_PROXY_SERVICE_TOKEN is missing")
	}
}

// TestLoad_ServiceTokenPresent verifies MINTKEY_EMAIL_PROXY_SERVICE_TOKEN is loaded.
func TestLoad_ServiceTokenPresent(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "my_shared_secret_token")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.EmailProxyServiceToken != "my_shared_secret_token" {
		t.Errorf("EmailProxyServiceToken = %q, want my_shared_secret_token", cfg.EmailProxyServiceToken)
	}
}

func TestLoad_BadHTTPPort(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_HTTP_PORT", "not-a-number")

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail with non-numeric HTTP port")
	}
}

func TestLoad_BadMetricsPort(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_METRICS_PORT", "not-a-number")

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail with non-numeric metrics port")
	}
}

func TestLoad_OutOfRangePort(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_HTTP_PORT", "99999")

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail with out-of-range port 99999")
	}
}

// TestMetricsPortDoesNotCollideWithSSHProxy documents the port collision avoidance.
// ssh-proxy uses :8087 for healthz; email-proxy uses :8090 for metrics.
func TestMetricsPortDoesNotCollideWithSSHProxy(t *testing.T) {
	os.Clearenv()
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "id_test")
	os.Setenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN", "tok_test")
	os.Setenv("MINTKEY_EMAIL_PROXY_SERVICE_TOKEN", "svc_tok_test")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	const sshProxyHealthzPort = 8087
	if cfg.MetricsPort == sshProxyHealthzPort {
		t.Errorf("MetricsPort %d collides with ssh-proxy healthz port %d", cfg.MetricsPort, sshProxyHealthzPort)
	}
}
