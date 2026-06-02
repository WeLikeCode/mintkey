// Package config provides configuration loading for the Email Proxy.
//
// All configuration is driven by environment variables. Required variables
// (MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID, MINTKEY_VAULT_EMAIL_PROXY_TOKEN)
// cause Load to return an error if absent, following the ssh-proxy fail-fast
// pattern (ADR-0024).
package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds all configuration for the Email Proxy.
type Config struct {
	// Vault identity for outbound vault calls.
	// Required: MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID
	VaultIdentityID string

	// Vault token for outbound vault calls.
	// Required: MINTKEY_VAULT_EMAIL_PROXY_TOKEN
	VaultToken string

	// BrokerJWKSURL is the full URL of the broker's JWKS endpoint.
	// Default: http://broker:8083/.well-known/jwks.json
	BrokerJWKSURL string

	// VaultGRPCAddr is the host:port of the vault-adapter gRPC service.
	// Default: vault-adapter:8084
	VaultGRPCAddr string

	// HTTPPort is the port for the main HTTP server (/healthz, /readyz, /metrics, /v1/...).
	// Default: 8088
	HTTPPort int

	// MetricsPort is the port for the dedicated Prometheus metrics endpoint.
	// Default: 8090 (NOT 8087 — that collides with ssh-proxy healthz).
	MetricsPort int

	// LogLevel controls structured logging verbosity.
	// Default: info
	LogLevel string

	// AdminAPIInternalURL is the internal URL of the admin-api service.
	// Used for the OAuth2 refresh callback.
	// Default: http://admin-api:8080
	AdminAPIInternalURL string

	// OTelEndpoint is the OTLP gRPC endpoint, e.g. "otel-collector:4317".
	OTelEndpoint string
}

// Load loads configuration from environment variables.
// Returns an error if any required variable is missing or any value is invalid.
func Load() (*Config, error) {
	cfg := &Config{
		BrokerJWKSURL:       "http://broker:8083/.well-known/jwks.json",
		VaultGRPCAddr:       "vault-adapter:8084",
		HTTPPort:            8088,
		MetricsPort:         8090,
		LogLevel:            "info",
		AdminAPIInternalURL: "http://admin-api:8080",
	}

	// Required vars — fail fast.
	if v := os.Getenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID"); v != "" {
		cfg.VaultIdentityID = v
	} else {
		return nil, fmt.Errorf("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID is required but not set")
	}

	if v := os.Getenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN"); v != "" {
		cfg.VaultToken = v
	} else {
		return nil, fmt.Errorf("MINTKEY_VAULT_EMAIL_PROXY_TOKEN is required but not set")
	}

	// Optional overrides.
	if v := os.Getenv("MINTKEY_BROKER_JWKS_URL"); v != "" {
		cfg.BrokerJWKSURL = v
	}

	if v := os.Getenv("MINTKEY_VAULT_GRPC_ADDR"); v != "" {
		cfg.VaultGRPCAddr = v
	}

	if v := os.Getenv("MINTKEY_EMAIL_PROXY_HTTP_PORT"); v != "" {
		port, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("invalid MINTKEY_EMAIL_PROXY_HTTP_PORT %q: %w", v, err)
		}
		if port < 1 || port > 65535 {
			return nil, fmt.Errorf("invalid MINTKEY_EMAIL_PROXY_HTTP_PORT %d: must be 1-65535", port)
		}
		cfg.HTTPPort = port
	}

	if v := os.Getenv("MINTKEY_EMAIL_PROXY_METRICS_PORT"); v != "" {
		port, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("invalid MINTKEY_EMAIL_PROXY_METRICS_PORT %q: %w", v, err)
		}
		if port < 1 || port > 65535 {
			return nil, fmt.Errorf("invalid MINTKEY_EMAIL_PROXY_METRICS_PORT %d: must be 1-65535", port)
		}
		cfg.MetricsPort = port
	}

	if v := os.Getenv("MINTKEY_EMAIL_PROXY_LOG_LEVEL"); v != "" {
		cfg.LogLevel = v
	}

	if v := os.Getenv("MINTKEY_ADMIN_API_INTERNAL_URL"); v != "" {
		cfg.AdminAPIInternalURL = v
	}

	if v := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"); v != "" {
		cfg.OTelEndpoint = v
	}

	return cfg, nil
}
