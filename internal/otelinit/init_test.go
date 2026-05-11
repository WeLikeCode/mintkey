package otelinit_test

import (
	"context"
	"testing"

	"github.com/mintkey/mintkey/internal/otelinit"
)

// TestRedactAttributes_ExactMatch verifies that exact forbidden attribute names
// are redacted (ADR-0017.6).
func TestRedactAttributes_ExactMatch(t *testing.T) {
	input := map[string]any{
		"http.request.header.authorization": "Bearer secret-token",
		"db.statement":                      "SELECT * FROM users",
		"messaging.message.payload":         `{"data":"sensitive"}`,
	}
	got := otelinit.RedactAttributes(input)
	for key := range input {
		if got[key] != "[REDACTED]" {
			t.Errorf("RedactAttributes()[%q] = %v, want [REDACTED]", key, got[key])
		}
	}
}

// TestRedactAttributes_SuffixToken verifies *_token suffix pattern.
func TestRedactAttributes_SuffixToken(t *testing.T) {
	input := map[string]any{
		"api_token":     "tok-abc123",
		"service_secret": "s3cr3t",
	}
	got := otelinit.RedactAttributes(input)
	for key := range input {
		if got[key] != "[REDACTED]" {
			t.Errorf("RedactAttributes()[%q] = %v, want [REDACTED]", key, got[key])
		}
	}
}

// TestRedactAttributes_SuffixPassword verifies *_password and *_passphrase suffix patterns.
func TestRedactAttributes_SuffixPassword(t *testing.T) {
	input := map[string]any{
		"user_password": "hunter2",
		"db_passphrase": "correct-horse-battery",
	}
	got := otelinit.RedactAttributes(input)
	for key := range input {
		if got[key] != "[REDACTED]" {
			t.Errorf("RedactAttributes()[%q] = %v, want [REDACTED]", key, got[key])
		}
	}
}

// TestRedactAttributes_SuffixKey verifies *_key suffix pattern.
func TestRedactAttributes_SuffixKey(t *testing.T) {
	input := map[string]any{
		"signing_key":    "ed25519-private-material",
		"encryption_key": "aes256-key-bytes",
	}
	got := otelinit.RedactAttributes(input)
	for key := range input {
		if got[key] != "[REDACTED]" {
			t.Errorf("RedactAttributes()[%q] = %v, want [REDACTED]", key, got[key])
		}
	}
}

// TestRedactAttributes_SuffixHash verifies *_hash suffix is redacted but safe
// attributes like event_type are untouched.
func TestRedactAttributes_SuffixHash(t *testing.T) {
	input := map[string]any{
		"password_hash": "argon2id$...",
		"event_type":    "user.created",
	}
	got := otelinit.RedactAttributes(input)
	if got["password_hash"] != "[REDACTED]" {
		t.Errorf("RedactAttributes()[\"password_hash\"] = %v, want [REDACTED]", got["password_hash"])
	}
	if got["event_type"] != "user.created" {
		t.Errorf("RedactAttributes()[\"event_type\"] = %v, want user.created", got["event_type"])
	}
}

// TestRedactAttributes_SafeAttributes verifies that standard OTel attributes
// are passed through unmodified.
func TestRedactAttributes_SafeAttributes(t *testing.T) {
	input := map[string]any{
		"service.name":    "admin-api",
		"http.method":     "GET",
		"http.status_code": 200,
	}
	got := otelinit.RedactAttributes(input)
	for key, want := range input {
		if got[key] != want {
			t.Errorf("RedactAttributes()[%q] = %v, want %v", key, got[key], want)
		}
	}
}

// TestInit_ReturnsShutdown verifies that Init returns a non-nil shutdown
// function without error even when the OTLP endpoint is unreachable. OTLP
// uses async export so connection failure does not block Init.
func TestInit_ReturnsShutdown(t *testing.T) {
	ctx := context.Background()
	shutdown, err := otelinit.Init(ctx, "test-service", "localhost:19999")
	if err != nil {
		t.Fatalf("Init() returned unexpected error: %v", err)
	}
	if shutdown == nil {
		t.Fatal("Init() returned nil shutdown function")
	}
	// Clean up; ignore error from shutdown since the exporter was never connected.
	_ = shutdown(ctx)
}
