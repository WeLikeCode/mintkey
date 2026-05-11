// Package config loads Vault Adapter runtime configuration from environment variables.
//
// Source: design §8; T-1.0.4.
package config

import (
	"os"
	"strconv"
)

// Config holds all runtime configuration for the Vault Adapter.
type Config struct {
	Env      string // "dev" | "production"
	GRPCPort int
	// MINTKEY_VAULT_KEK_FILE and MINTKEY_VAULT_KEK are consumed by kek.Load() directly.
}

// Load reads configuration from environment variables.
func Load() *Config {
	return &Config{
		Env:      getEnv("MINTKEY_ENV", "dev"),
		GRPCPort: getEnvInt("VAULT_GRPC_PORT", 8084),
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
