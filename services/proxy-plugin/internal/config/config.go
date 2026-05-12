// Package config loads Egress Proxy plugin runtime configuration from
// environment variables.
//
// Source: design §10; ADR-0004; T-1.0.7.
package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds all runtime configuration for the proxy plugin.
type Config struct {
	Env              string // "dev" | "production"
	VaultAddrGRPC    string // host:port of the Vault Adapter gRPC endpoint
	JWKSEndpoint     string // URL of the broker's /.well-known/jwks.json
	PluginSocket     string // Unix socket path for the go-pdk server (future)
	PluginPort       int    // HTTP listen port for the reverse proxy
	DefaultTarget    string // fallback upstream URL when X-Mintkey-Target header absent
	BrokerBaseURL    string // base URL for broker's /v1/api-keys/resolve (ADR-0018)
	ProxyServiceToken string // X-Mintkey-Service-Token for broker auth (ADR-0018)
}

// Load reads configuration from environment variables, applying sensible
// defaults suitable for docker-compose local development.
func Load() *Config {
	brokerAddr := getEnv("BROKER_ADDR", "broker:8083")
	brokerBaseURL := getEnv("BROKER_BASE_URL", fmt.Sprintf("http://%s", brokerAddr))
	return &Config{
		Env:               getEnv("MINTKEY_ENV", "dev"),
		VaultAddrGRPC:     getEnv("VAULT_GRPC_ADDR", "vault-adapter:8084"),
		JWKSEndpoint:      fmt.Sprintf("http://%s/.well-known/jwks.json", brokerAddr),
		PluginSocket:      getEnv("PLUGIN_SOCKET", "/tmp/proxy-plugin.sock"),
		PluginPort:        getEnvInt("PLUGIN_PORT", 8086),
		DefaultTarget:     getEnv("DEFAULT_TARGET", ""),
		BrokerBaseURL:     brokerBaseURL,
		ProxyServiceToken: getEnv("MINTKEY_PROXY_SERVICE_TOKEN", ""),
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
