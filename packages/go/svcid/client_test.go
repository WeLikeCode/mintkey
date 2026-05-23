package svcid_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/mintkey/mintkey/packages/go/svcid"
)

func TestNewClient_ReadsTokenFromFile(t *testing.T) {
	dir := t.TempDir()
	tokenFile := filepath.Join(dir, "token")
	if err := os.WriteFile(tokenFile, []byte("tok-abc-123"), 0600); err != nil {
		t.Fatalf("write temp file: %v", err)
	}

	c, err := svcid.NewClient(tokenFile)
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}

	got, err := c.Token()
	if err != nil {
		t.Fatalf("Token: %v", err)
	}
	if got != "tok-abc-123" {
		t.Errorf("Token() = %q, want %q", got, "tok-abc-123")
	}
}

func TestNewClient_RotatesOnFileChange(t *testing.T) {
	dir := t.TempDir()
	tokenFile := filepath.Join(dir, "token")
	if err := os.WriteFile(tokenFile, []byte("token-A"), 0600); err != nil {
		t.Fatalf("write temp file: %v", err)
	}

	c, err := svcid.NewClient(tokenFile)
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}

	gotA, err := c.Token()
	if err != nil {
		t.Fatalf("Token (A): %v", err)
	}
	if gotA != "token-A" {
		t.Errorf("Token() = %q, want %q", gotA, "token-A")
	}

	// Overwrite with new token
	if err := os.WriteFile(tokenFile, []byte("token-B"), 0600); err != nil {
		t.Fatalf("overwrite temp file: %v", err)
	}

	gotB, err := c.Token()
	if err != nil {
		t.Fatalf("Token (B): %v", err)
	}
	if gotB != "token-B" {
		t.Errorf("after rotation Token() = %q, want %q", gotB, "token-B")
	}
}

func TestNewClient_MissingFile_Errors(t *testing.T) {
	_, err := svcid.NewClient("/nonexistent/path/to/token")
	if err == nil {
		t.Error("NewClient with missing file should return error, got nil")
	}
}
