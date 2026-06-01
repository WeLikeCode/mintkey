// Package config provides configuration loading for the SSH Proxy.
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config holds all configuration for the SSH Proxy.
type Config struct {
	// SSH server configuration
	SSHAddr         string
	HostKeyPath     string
	HostKeyGenerate bool // default false — operator must seed via make ssh-proxy-init (G)

	// HTTP server configuration (health/metrics)
	HTTPAddr string

	// Vault Adapter connection
	VaultAddr string

	// Broker connection (for JWKS)
	BrokerAddr string

	// Database connection (for change channel subscription)
	DatabaseURL string

	// Session management
	SessionTimeout                time.Duration
	SessionIdleTimeout            time.Duration // B14: idle timeout; 0 = disabled
	MaxConcurrentSessionsPerAgent int

	// Recording
	RecordingEnabled     bool
	RecordingStoragePath string
	RecordingRetention   time.Duration

	// Command filtering
	CommandFilterMode string // "allowlist" or "denylist"

	// OTel configuration: OTLP gRPC endpoint, e.g. "otel-collector:4317".
	OTelEndpoint string

	// Vault identity for outbound vault calls (C1: empty default; C3 wires real values).
	VaultIdentityID string
	VaultToken      string

	// TOFU host-key strict mode (A): when true, reject unknown host keys.
	// Default false (dev); set SSH_PROXY_HOSTKEY_STRICT=true in production.
	HostKeyStrict bool

	// Password auth (allow JWT-in-password slot) — default true until ssh_pubkey
	// is wired in C7, at which point it can default false.
	AllowPasswordAuth bool

	// Rate limiting (B20)
	RateLimitPerSecond float64 // token-bucket refill rate
	RateLimitBurst     int     // token-bucket burst size
	MaxConcurrentHandshakes int // semaphore size for unauthenticated handshakes
}

// Load loads configuration from environment variables and optional config file.
func Load(configPath string) (*Config, error) {
	cfg := &Config{
		// Defaults
		SSHAddr:                       ":2222",
		HTTPAddr:                      ":8087",
		HostKeyPath:                   "/etc/ssh/ssh_host_ed25519_key",
		HostKeyGenerate:               false, // G: operator must seed key
		SessionTimeout:                1 * time.Hour,
		SessionIdleTimeout:            0, // disabled by default
		MaxConcurrentSessionsPerAgent: 5,
		RecordingEnabled:              true,
		RecordingStoragePath:          "/var/lib/mintkey/ssh-recordings",
		RecordingRetention:            30 * 24 * time.Hour, // 30 days
		CommandFilterMode:             "denylist",
		HostKeyStrict:                 false, // set true in production
		AllowPasswordAuth:             true,  // JWT-in-password slot; C7 can flip to false
		RateLimitPerSecond:            10,
		RateLimitBurst:                20,
		MaxConcurrentHandshakes:       200,
	}

	// Override from environment
	if v := os.Getenv("SSH_PROXY_ADDR"); v != "" {
		cfg.SSHAddr = v
	}
	if v := os.Getenv("SSH_PROXY_HTTP_ADDR"); v != "" {
		cfg.HTTPAddr = v
	}
	if v := os.Getenv("SSH_PROXY_HOST_KEY_PATH"); v != "" {
		cfg.HostKeyPath = v
	}
	if v := os.Getenv("SSH_PROXY_HOST_KEY_GENERATE"); v != "" {
		cfg.HostKeyGenerate = v == "true" || v == "1"
	}
	if v := os.Getenv("SSH_PROXY_HOSTKEY_STRICT"); v != "" {
		cfg.HostKeyStrict = v == "true" || v == "1"
	}

	if v := os.Getenv("VAULT_ADAPTER_ADDR"); v != "" {
		cfg.VaultAddr = v
	} else {
		cfg.VaultAddr = "localhost:8200"
	}

	if v := os.Getenv("BROKER_ADDR"); v != "" {
		cfg.BrokerAddr = v
	} else {
		cfg.BrokerAddr = "localhost:8080"
	}

	if v := os.Getenv("DATABASE_URL"); v != "" {
		cfg.DatabaseURL = v
	}

	if v := os.Getenv("SSH_SESSION_TIMEOUT"); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			return nil, fmt.Errorf("invalid SSH_SESSION_TIMEOUT: %w", err)
		}
		cfg.SessionTimeout = d
	}

	if v := os.Getenv("SSH_SESSION_IDLE_TIMEOUT"); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			return nil, fmt.Errorf("invalid SSH_SESSION_IDLE_TIMEOUT: %w", err)
		}
		cfg.SessionIdleTimeout = d
	}

	if v := os.Getenv("SSH_MAX_SESSIONS_PER_AGENT"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("invalid SSH_MAX_SESSIONS_PER_AGENT: %w", err)
		}
		cfg.MaxConcurrentSessionsPerAgent = n
	}

	if v := os.Getenv("SSH_RECORDING_ENABLED"); v != "" {
		cfg.RecordingEnabled = v == "true" || v == "1"
	}

	if v := os.Getenv("SSH_RECORDING_STORAGE_PATH"); v != "" {
		cfg.RecordingStoragePath = v
	}

	if v := os.Getenv("SSH_RECORDING_RETENTION"); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			return nil, fmt.Errorf("invalid SSH_RECORDING_RETENTION: %w", err)
		}
		cfg.RecordingRetention = d
	}

	if v := os.Getenv("SSH_COMMAND_FILTER_MODE"); v != "" {
		if v != "allowlist" && v != "denylist" {
			return nil, fmt.Errorf("invalid SSH_COMMAND_FILTER_MODE: must be 'allowlist' or 'denylist'")
		}
		cfg.CommandFilterMode = v
	}

	// OTel endpoint override.
	if v := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"); v != "" {
		cfg.OTelEndpoint = v
	}

	// Vault identity fields (C3 wires real values via MINTKEY_VAULT_SSH_PROXY_*).
	if v := os.Getenv("MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID"); v != "" {
		cfg.VaultIdentityID = v
	}
	if v := os.Getenv("MINTKEY_VAULT_SSH_PROXY_TOKEN"); v != "" {
		cfg.VaultToken = v
	}

	// Rate limiting overrides.
	if v := os.Getenv("SSH_RATE_LIMIT_PER_SECOND"); v != "" {
		f, err := strconv.ParseFloat(v, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid SSH_RATE_LIMIT_PER_SECOND: %w", err)
		}
		cfg.RateLimitPerSecond = f
	}
	if v := os.Getenv("SSH_RATE_LIMIT_BURST"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("invalid SSH_RATE_LIMIT_BURST: %w", err)
		}
		cfg.RateLimitBurst = n
	}
	if v := os.Getenv("SSH_MAX_CONCURRENT_HANDSHAKES"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("invalid SSH_MAX_CONCURRENT_HANDSHAKES: %w", err)
		}
		cfg.MaxConcurrentHandshakes = n
	}

	return cfg, nil
}
