// Package config loads Credential Broker runtime configuration.
//
// Source: design §7; T-1.0.5.
package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/packages/go/svcid"
)

// Config holds all runtime configuration for the Credential Broker.
type Config struct {
	Env               string
	HTTPPort          int
	VaultGRPCAddr     string // host:port of the Vault Adapter
	SigningKeyFile    string // path to 32-byte seed file (MINTKEY_BROKER_SIGNING_KEY_FILE)
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
	secretErr    error
}

// SecretErr returns the error of reading the service tokens in Load, or nil.
func (c *Config) SecretErr() error {
	return c.secretErr
}

// Load reads configuration from environment variables.
func Load() *Config {
	serviceToken, serviceErr := svcid.FromEnv("MINTKEY_SERVICE_TOKEN")
	proxyServiceToken, proxyErr := svcid.FromEnv("MINTKEY_PROXY_SERVICE_TOKEN")
	mcpServiceToken, mcpErr := svcid.FromEnv("MINTKEY_MCP_SERVICE_TOKEN")
	brokerSvcToken, brokerErr := svcid.FromEnv("MINTKEY_BROKER_SERVICE_TOKEN")
	return &Config{
		Env:               getEnv("MINTKEY_ENV", "dev"),
		HTTPPort:          getEnvInt("BROKER_HTTP_PORT", 8083),
		VaultGRPCAddr:     getEnv("VAULT_GRPC_ADDR", "vault-adapter:8084"),
		SigningKeyFile:    os.Getenv("MINTKEY_BROKER_SIGNING_KEY_FILE"),
		ServiceToken:      serviceToken,      // /run/secrets/ in compose
		ProxyServiceToken: proxyServiceToken, // /run/secrets/ in compose
		MCPServiceToken:   mcpServiceToken,   // shared with MCP Server
		DatabaseURL:       getEnv("DATABASE_URL", ""),
		// Audit async emission (#22)
		AdminAPIURL:    getEnv("MINTKEY_ADMIN_API_URL", "http://admin-api:8000"),
		BrokerSvcToken: brokerSvcToken,
		AuditWALPath:   getEnv("MINTKEY_AUDIT_WAL_PATH", "/var/lib/mintkey/broker-audit.wal"),
		// WAL compaction (#27)
		AuditCompact: auditq.CompactConfig{
			IntervalSec:    getEnvInt("MINTKEY_AUDIT_WAL_COMPACT_INTERVAL_SEC", 300),
			ThresholdBytes: getEnvInt64("MINTKEY_AUDIT_WAL_COMPACT_THRESHOLD_BYTES", 64<<20),
		},
		secretErr: errors.Join(serviceErr, proxyErr, mcpErr, brokerErr),
	}
}

// MissingServiceTokens returns the names of the inbound service-token variables whose value is empty, in the order
// MINTKEY_MCP_SERVICE_TOKEN, MINTKEY_PROXY_SERVICE_TOKEN. It returns an empty (nil) slice when both are set.
func (c *Config) MissingServiceTokens() []string {
	var missing []string
	if c.MCPServiceToken == "" {
		missing = append(missing, "MINTKEY_MCP_SERVICE_TOKEN")
	}
	if c.ProxyServiceToken == "" {
		missing = append(missing, "MINTKEY_PROXY_SERVICE_TOKEN")
	}
	return missing
}

// Validate returns nil unless c.Env == "production" and MissingServiceTokens() is not empty. Then it returns an error
// whose message is "production requires these variables to be set: " + strings.Join(MissingServiceTokens(), ", ").
func (c *Config) Validate() error {
	missing := c.MissingServiceTokens()
	if c.Env == "production" && len(missing) != 0 {
		return fmt.Errorf("production requires these variables to be set: %s", strings.Join(missing, ", "))
	}
	return nil
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
