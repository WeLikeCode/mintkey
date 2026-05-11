// Package config loads kong-syncer runtime configuration.
//
// Source: design §9; T-1.0.6.
package config

import (
	"os"
	"strconv"
)

// Config holds all runtime configuration for kong-syncer.
type Config struct {
	Env         string
	HTTPPort    int
	DatabaseURL string
	KongAdminURL string
}

// Load reads configuration from environment variables.
func Load() *Config {
	return &Config{
		Env:          getEnv("MINTKEY_ENV", "dev"),
		HTTPPort:     getEnvInt("KONG_SYNCER_HTTP_PORT", 8086),
		DatabaseURL:  getEnv("DATABASE_URL", "postgres://mintkey:mintkey@localhost:5432/mintkey?sslmode=disable"),
		KongAdminURL: getEnv("KONG_ADMIN_URL", "http://kong:8001"),
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
