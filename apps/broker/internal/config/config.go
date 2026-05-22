// Package config loads Credential Broker runtime configuration.
//
// Source: design §7; T-1.0.5.
package config

import (
	"os"
	"strconv"

	"github.com/mintkey/mintkey/internal/auditq"
)

// Config holds all runtime configuration for the Credential Broker.
type Config struct {
	Env               string
	HTTPPort          int
	VaultGRPCAddr     string // host:port of the Vault Adapter
	ServiceToken      string // svcid_broker boot secret (from /run/secrets/mintkey_service_token)
	ProxyServiceToken string // shared secret the Egress Proxy must supply for /v1/api-keys/resolve
	MCPServiceToken   string // shared secret the MCP Server must supply for /v1/issue
	DatabaseURL       string // postgres DSN for api-key resolution queries
	// Audit async emission (#22)
	AdminAPIURL    string // base URL of admin-api for audit/emit (e.g. http://admin-api:8000)
	BrokerSvcToken string // X-Mintkey-Service-Token sent to admin-api audit/emit
	AuditWALPath   string // path to the WAL file (default /var/lib/mintkey/broker-audit.wal)
	// WAL compaction (#27)
	AuditCompact auditq.CompactConfig
}

// Load reads configuration from environment variables.
func Load() *Config {
	return &Config{
		Env:               getEnv("MINTKEY_ENV", "dev"),
		HTTPPort:          getEnvInt("BROKER_HTTP_PORT", 8083),
		VaultGRPCAddr:     getEnv("VAULT_GRPC_ADDR", "vault-adapter:8084"),
		ServiceToken:      os.Getenv("MINTKEY_SERVICE_TOKEN"),        // /run/secrets/ in compose
		ProxyServiceToken: os.Getenv("MINTKEY_PROXY_SERVICE_TOKEN"),  // /run/secrets/ in compose
		MCPServiceToken:   os.Getenv("MINTKEY_MCP_SERVICE_TOKEN"),    // shared with MCP Server
		DatabaseURL:       getEnv("DATABASE_URL", ""),
		// Audit async emission (#22)
		AdminAPIURL:    getEnv("MINTKEY_ADMIN_API_URL", "http://admin-api:8000"),
		BrokerSvcToken: os.Getenv("MINTKEY_BROKER_SERVICE_TOKEN"),
		AuditWALPath:   getEnv("MINTKEY_AUDIT_WAL_PATH", "/var/lib/mintkey/broker-audit.wal"),
		// WAL compaction (#27)
		AuditCompact: auditq.CompactConfig{
			IntervalSec:    getEnvInt("MINTKEY_AUDIT_WAL_COMPACT_INTERVAL_SEC", 300),
			ThresholdBytes: getEnvInt64("MINTKEY_AUDIT_WAL_COMPACT_THRESHOLD_BYTES", 64<<20),
		},
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

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
