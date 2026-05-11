// Package config loads Credential Broker runtime configuration.
//
// Source: design §7; T-1.0.5.
package config

import (
	"os"
	"strconv"
)

// Config holds all runtime configuration for the Credential Broker.
type Config struct {
	Env              string
	HTTPPort         int
	VaultGRPCAddr    string // host:port of the Vault Adapter
	ServiceToken     string // svcid_broker boot secret (from /run/secrets/mintkey_service_token)
	ProxyServiceToken string // shared secret the Egress Proxy must supply for /v1/api-keys/resolve
	DatabaseURL      string // postgres DSN for api-key resolution queries
}

// Load reads configuration from environment variables.
func Load() *Config {
	return &Config{
		Env:               getEnv("MINTKEY_ENV", "dev"),
		HTTPPort:          getEnvInt("BROKER_HTTP_PORT", 8083),
		VaultGRPCAddr:     getEnv("VAULT_GRPC_ADDR", "vault-adapter:8084"),
		ServiceToken:      os.Getenv("MINTKEY_SERVICE_TOKEN"),        // /run/secrets/ in compose
		ProxyServiceToken: os.Getenv("MINTKEY_PROXY_SERVICE_TOKEN"),  // /run/secrets/ in compose
		DatabaseURL:       getEnv("DATABASE_URL", ""),
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
