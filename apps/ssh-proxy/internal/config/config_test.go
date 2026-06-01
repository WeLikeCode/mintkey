package config

import (
	"os"
	"testing"
	"time"
)

func TestLoad_Defaults(t *testing.T) {
	// Clear environment
	os.Clearenv()

	cfg, err := Load("")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	// Check defaults
	if cfg.SSHAddr != ":2222" {
		t.Errorf("SSHAddr = %q, want %q", cfg.SSHAddr, ":2222")
	}
	if cfg.HTTPAddr != ":8087" {
		t.Errorf("HTTPAddr = %q, want %q", cfg.HTTPAddr, ":8087")
	}
	if cfg.SessionTimeout != 1*time.Hour {
		t.Errorf("SessionTimeout = %v, want %v", cfg.SessionTimeout, 1*time.Hour)
	}
	if cfg.MaxConcurrentSessionsPerAgent != 5 {
		t.Errorf("MaxConcurrentSessionsPerAgent = %d, want %d", cfg.MaxConcurrentSessionsPerAgent, 5)
	}
	if !cfg.RecordingEnabled {
		t.Error("RecordingEnabled = false, want true")
	}
	if cfg.CommandFilterMode != "denylist" {
		t.Errorf("CommandFilterMode = %q, want %q", cfg.CommandFilterMode, "denylist")
	}
}

func TestLoad_EnvironmentOverrides(t *testing.T) {
	os.Clearenv()
	os.Setenv("SSH_PROXY_ADDR", ":3333")
	os.Setenv("SSH_PROXY_HTTP_ADDR", ":9090")
	os.Setenv("SSH_SESSION_TIMEOUT", "2h")
	os.Setenv("SSH_MAX_SESSIONS_PER_AGENT", "10")
	os.Setenv("SSH_RECORDING_ENABLED", "false")
	os.Setenv("SSH_COMMAND_FILTER_MODE", "allowlist")

	cfg, err := Load("")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.SSHAddr != ":3333" {
		t.Errorf("SSHAddr = %q, want %q", cfg.SSHAddr, ":3333")
	}
	if cfg.HTTPAddr != ":9090" {
		t.Errorf("HTTPAddr = %q, want %q", cfg.HTTPAddr, ":9090")
	}
	if cfg.SessionTimeout != 2*time.Hour {
		t.Errorf("SessionTimeout = %v, want %v", cfg.SessionTimeout, 2*time.Hour)
	}
	if cfg.MaxConcurrentSessionsPerAgent != 10 {
		t.Errorf("MaxConcurrentSessionsPerAgent = %d, want %d", cfg.MaxConcurrentSessionsPerAgent, 10)
	}
	if cfg.RecordingEnabled {
		t.Error("RecordingEnabled = true, want false")
	}
	if cfg.CommandFilterMode != "allowlist" {
		t.Errorf("CommandFilterMode = %q, want %q", cfg.CommandFilterMode, "allowlist")
	}
}

func TestLoad_InvalidSessionTimeout(t *testing.T) {
	os.Clearenv()
	os.Setenv("SSH_SESSION_TIMEOUT", "invalid")

	_, err := Load("")
	if err == nil {
		t.Error("Load() expected error for invalid SSH_SESSION_TIMEOUT")
	}
}

func TestLoad_InvalidMaxSessions(t *testing.T) {
	os.Clearenv()
	os.Setenv("SSH_MAX_SESSIONS_PER_AGENT", "not-a-number")

	_, err := Load("")
	if err == nil {
		t.Error("Load() expected error for invalid SSH_MAX_SESSIONS_PER_AGENT")
	}
}

func TestLoad_InvalidCommandFilterMode(t *testing.T) {
	os.Clearenv()
	os.Setenv("SSH_COMMAND_FILTER_MODE", "invalid")

	_, err := Load("")
	if err == nil {
		t.Error("Load() expected error for invalid SSH_COMMAND_FILTER_MODE")
	}
}

func TestLoad_InvalidRecordingRetention(t *testing.T) {
	os.Clearenv()
	os.Setenv("SSH_RECORDING_RETENTION", "invalid")

	_, err := Load("")
	if err == nil {
		t.Error("Load() expected error for invalid SSH_RECORDING_RETENTION")
	}
}
