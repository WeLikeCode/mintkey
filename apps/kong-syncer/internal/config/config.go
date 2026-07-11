// Package config loads kong-syncer runtime configuration.
//
// Source: design §9; T-1.0.6.
package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds all runtime configuration for kong-syncer.
type Config struct {
	Env          string
	HTTPPort     int
	DatabaseURL  string
	KongAdminURL string

	// ProxyPluginURL is the upstream every generated Kong service routes to —
	// the proxy-plugin that validates JWTs, fetches credentials from the Vault
	// Adapter, and reverse-proxies. Env: PROXY_PLUGIN_URL. Default:
	// http://proxy-plugin:8086 (the docker-compose service name). On Kubernetes
	// the Service is release-name-prefixed, so this MUST be overridden to e.g.
	// http://mintkey-proxy-plugin:8086, otherwise Kong returns
	// "name resolution failed" for every brokered call.
	ProxyPluginURL string

	// InitialRetryMaxDuration caps the total wall-clock time spent retrying
	// the initial reconcile at startup. Env: KONG_SYNCER_INITIAL_RETRY_MAX_DURATION.
	// Default: 5m.
	InitialRetryMaxDuration time.Duration

	// PeriodicInterval is how often the periodic safety-net reconcile fires.
	// A value of 0 disables the periodic safety-net entirely.
	// Env: KONG_SYNCER_PERIODIC_INTERVAL. Default: 5m.
	PeriodicInterval time.Duration
}

// Load reads configuration from environment variables.
func Load() *Config {
	return &Config{
		Env:                     getEnv("MINTKEY_ENV", "dev"),
		HTTPPort:                getEnvInt("KONG_SYNCER_HTTP_PORT", 8086),
		DatabaseURL:             getEnv("DATABASE_URL", "postgres://mintkey:mintkey@localhost:5432/mintkey?sslmode=disable"),
		KongAdminURL:            getEnv("KONG_ADMIN_URL", "http://kong:8001"),
		ProxyPluginURL:          getEnv("PROXY_PLUGIN_URL", "http://proxy-plugin:8086"),
		InitialRetryMaxDuration: getEnvDuration("KONG_SYNCER_INITIAL_RETRY_MAX_DURATION", 5*time.Minute),
		PeriodicInterval:        getEnvDuration("KONG_SYNCER_PERIODIC_INTERVAL", 5*time.Minute),
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

// getEnvDuration parses a duration string from the environment. The special
// value "off" maps to 0 (disabled). Returns fallback if the variable is unset
// or unparseable.
func getEnvDuration(key string, fallback time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	if v == "off" || v == "0" {
		return 0
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return fallback
	}
	return d
}
