// Package security_test provides red-team focused tests for security primitives.
package security_test

import (
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
)

// ---------------------------------------------------------------------------
// RFC 5322 address parser tests
// ---------------------------------------------------------------------------

func TestParseAddressList_HappyPath(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  int // expected number of addresses
	}{
		{"single plain", "user@example.com", 1},
		{"display name", `"Alice Smith" <alice@example.com>`, 1},
		{"multiple", "a@x.com, b@y.org", 2},
		{"unicode display name", `"Ünïcödé User" <u@example.com>`, 1},
		{"subaddress", "user+tag@example.com", 1},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			addrs, err := security.ParseAddressList(tt.input)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if len(addrs) != tt.want {
				t.Fatalf("got %d addresses, want %d", len(addrs), tt.want)
			}
		})
	}
}

func TestParseAddressList_CRLF_Injection(t *testing.T) {
	// NFR-19: any \r or \n must be rejected immediately.
	payloads := []string{
		"user@example.com\r\nBcc: attacker@evil.com",
		"user@example.com\rX-Injected: bad",
		"user@example.com\nBcc: attacker@evil.com",
		"user\r@example.com",
		"\"Name\r\nInjected\" <user@example.com>",
	}
	for _, p := range payloads {
		if _, err := security.ParseAddressList(p); err == nil {
			t.Errorf("expected rejection for payload %q, got nil error", p)
		}
	}
}

func TestParseAddressList_ControlChars(t *testing.T) {
	// Any control char 0x00-0x1F (except \t which net/mail allows in display names)
	// or 0x7F (DEL) must be rejected.
	payloads := []string{
		"user\x00@example.com",
		"user\x01@example.com",
		"user\x7f@example.com",
		"\x0b" + "user@example.com",
	}
	for _, p := range payloads {
		if _, err := security.ParseAddressList(p); err == nil {
			t.Errorf("expected rejection for control-char payload %q, got nil error", p)
		}
	}
}

func TestParseAddressList_LengthLimits(t *testing.T) {
	// local-part > 64 chars must be rejected.
	longLocal := strings.Repeat("a", 65) + "@example.com"
	if _, err := security.ParseAddressList(longLocal); err == nil {
		t.Errorf("expected rejection for local-part > 64 chars")
	}

	// domain > 255 chars must be rejected.
	longDomain := "user@" + strings.Repeat("a", 256) + ".com"
	if _, err := security.ParseAddressList(longDomain); err == nil {
		t.Errorf("expected rejection for domain > 255 chars")
	}

	// full address > 320 chars must be rejected.
	longFull := strings.Repeat("a", 65) + "@" + strings.Repeat("b", 256) + ".com"
	if _, err := security.ParseAddressList(longFull); err == nil {
		t.Errorf("expected rejection for full address > 320 chars")
	}
}

func TestParseAddressList_MissingAt(t *testing.T) {
	if _, err := security.ParseAddressList("notanemail"); err == nil {
		t.Error("expected error for address without @")
	}
}

func TestParseAddressList_IDN(t *testing.T) {
	// Internationalised domain names in ACE form must be accepted.
	addrs, err := security.ParseAddressList("user@xn--nxasmq6b.com")
	if err != nil {
		t.Fatalf("unexpected error for IDN address: %v", err)
	}
	if len(addrs) != 1 {
		t.Fatalf("expected 1 address, got %d", len(addrs))
	}
}

func TestParseAddressList_Empty(t *testing.T) {
	if _, err := security.ParseAddressList(""); err == nil {
		t.Error("expected error for empty string")
	}
}

func TestParseAddressList_OversizedInput(t *testing.T) {
	// An oversized raw input (> 1000 chars before any parse) must be rejected.
	huge := strings.Repeat("a@b.com, ", 200)
	if _, err := security.ParseAddressList(huge); err == nil {
		t.Error("expected rejection for oversized address list input")
	}
}
