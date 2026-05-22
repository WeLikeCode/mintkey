// Package config loads Egress Proxy plugin runtime configuration from
// environment variables.
//
// Source: design §10; ADR-0004; T-1.0.7.
package config

import (
	"fmt"
	"os"
	"strconv"

	"github.com/mintkey/mintkey/internal/auditq"
)

// AudEnforcement controls how the proxy-plugin enforces the JWT aud-vs-URL
// service_id check (ADR-0004 addendum — Scenario D / WS-4).
//
//   - Strict:     mismatch → 403 {"error":"scope mismatch"}.  Default in production.
//   - Permissive: mismatch → warning log, request proceeds.   Default in dev/test.
type AudEnforcement string

const (
	// AudEnforcementStrict rejects requests where JWT.aud != URL svc_id.
	AudEnforcementStrict AudEnforcement = "strict"
	// AudEnforcementPermissive logs a warning on mismatch but allows the request.
	AudEnforcementPermissive AudEnforcement = "permissive"
)

// Config holds all runtime configuration for the proxy plugin.
type Config struct {
	Env               string         // "dev" | "production"
	VaultAddrGRPC     string         // host:port of the Vault Adapter gRPC endpoint
	JWKSEndpoint      string         // URL of the broker's /.well-known/jwks.json
	PluginSocket      string         // Unix socket path for the go-pdk server (future)
	PluginPort        int            // HTTP listen port for the reverse proxy
	DefaultTarget     string         // fallback upstream URL when X-Mintkey-Target header absent
	BrokerBaseURL     string         // base URL for broker's /v1/api-keys/resolve (ADR-0018)
	ProxyServiceToken string         // X-Mintkey-Service-Token for broker auth (ADR-0018)
	AudEnforcement    AudEnforcement // strict | permissive (ADR-0004 addendum)
	// Audit async emission (#22)
	AdminAPIURL  string // base URL of admin-api for audit/emit (e.g. http://admin-api:8000)
	AuditWALPath string // path to the WAL file (default /var/lib/mintkey/proxy-audit.wal)
	// WAL compaction (#27)
	AuditCompact auditq.CompactConfig
}

// Load reads configuration from environment variables, applying sensible
// defaults suitable for docker-compose local development.
//
// MINTKEY_AUD_ENFORCEMENT defaults to "strict" when MINTKEY_ENV=production,
// and "permissive" otherwise (ADR-0004 addendum — Scenario D / WS-4).
func Load() *Config {
	brokerAddr := getEnv("BROKER_ADDR", "broker:8083")
	brokerBaseURL := getEnv("BROKER_BASE_URL", fmt.Sprintf("http://%s", brokerAddr))
	env := getEnv("MINTKEY_ENV", "dev")
	return &Config{
		Env:               env,
		VaultAddrGRPC:     getEnv("VAULT_GRPC_ADDR", "vault-adapter:8084"),
		JWKSEndpoint:      fmt.Sprintf("http://%s/.well-known/jwks.json", brokerAddr),
		PluginSocket:      getEnv("PLUGIN_SOCKET", "/tmp/proxy-plugin.sock"),
		PluginPort:        getEnvInt("PLUGIN_PORT", 8086),
		DefaultTarget:     getEnv("DEFAULT_TARGET", ""),
		BrokerBaseURL:     brokerBaseURL,
		ProxyServiceToken: getEnv("MINTKEY_PROXY_SERVICE_TOKEN", ""),
		AudEnforcement:    loadAudEnforcement(env),
		// Audit async emission (#22)
		AdminAPIURL:  getEnv("MINTKEY_ADMIN_API_URL", "http://admin-api:8000"),
		AuditWALPath: getEnv("MINTKEY_AUDIT_WAL_PATH", "/var/lib/mintkey/proxy-audit.wal"),
		// WAL compaction (#27)
		AuditCompact: auditq.CompactConfig{
			IntervalSec:    getEnvInt("MINTKEY_AUDIT_WAL_COMPACT_INTERVAL_SEC", 300),
			ThresholdBytes: getEnvInt64("MINTKEY_AUDIT_WAL_COMPACT_THRESHOLD_BYTES", 64<<20),
		},
	}
}

// loadAudEnforcement resolves the MINTKEY_AUD_ENFORCEMENT env var.
// If unset, defaults to "strict" in production and "permissive" elsewhere.
func loadAudEnforcement(env string) AudEnforcement {
	raw := os.Getenv("MINTKEY_AUD_ENFORCEMENT")
	switch AudEnforcement(raw) {
	case AudEnforcementStrict:
		return AudEnforcementStrict
	case AudEnforcementPermissive:
		return AudEnforcementPermissive
	default:
		// Unknown or empty — apply env-based default.
		if env == "production" {
			return AudEnforcementStrict
		}
		return AudEnforcementPermissive
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// getEnvInt is kept for future numeric config fields (e.g., JWKS cache TTL).
func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}

func getEnvInt64(key string, fallback int64) int64 {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.ParseInt(v, 10, 64); err == nil {
			return n
		}
	}
	return fallback
}
