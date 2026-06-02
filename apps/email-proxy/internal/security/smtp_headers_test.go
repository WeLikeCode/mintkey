package security_test

import (
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
)

// ---------------------------------------------------------------------------
// SMTP header injection sanitizer tests
// ---------------------------------------------------------------------------

func TestSanitizeHeader_Clean(t *testing.T) {
	name, value, err := security.SanitizeHeader("Subject", "Hello World")
	if err != nil {
		t.Fatalf("unexpected error for clean header: %v", err)
	}
	if name != "subject" {
		t.Errorf("header name should be lowercased; got %q", name)
	}
	if value != "Hello World" {
		t.Errorf("value should be unchanged; got %q", value)
	}
}

func TestSanitizeHeader_CRLF_Injection_Value(t *testing.T) {
	payloads := []string{
		"Hello\r\nBcc: attacker@evil.com",
		"Hello\rBcc: attacker@evil.com",
		"Hello\nBcc: attacker@evil.com",
		"Hello\r\n\tfolded header",
	}
	for _, p := range payloads {
		if _, _, err := security.SanitizeHeader("Subject", p); err == nil {
			t.Errorf("CRLF in value should be rejected: %q", p)
		}
	}
}

func TestSanitizeHeader_CRLF_Injection_Name(t *testing.T) {
	payloads := []string{
		"Sub\r\nject",
		"Sub\rject",
		"Sub\nject",
	}
	for _, p := range payloads {
		if _, _, err := security.SanitizeHeader(p, "value"); err == nil {
			t.Errorf("CRLF in header name should be rejected: %q", p)
		}
	}
}

func TestSanitizeHeader_OversizedValue(t *testing.T) {
	big := strings.Repeat("a", 1000)
	if _, _, err := security.SanitizeHeader("Subject", big); err == nil {
		t.Error("oversized header value should be rejected")
	}
}

func TestSanitizeHeader_OversizedName(t *testing.T) {
	big := strings.Repeat("X", 100)
	if _, _, err := security.SanitizeHeader(big, "value"); err == nil {
		t.Error("oversized header name should be rejected")
	}
}

func TestSanitizeHeader_LowercaseName(t *testing.T) {
	name, _, err := security.SanitizeHeader("X-CUSTOM-HEADER", "val")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if name != "x-custom-header" {
		t.Errorf("header name not lowercased: %q", name)
	}
}

func TestSanitizeHeader_EmptyName(t *testing.T) {
	if _, _, err := security.SanitizeHeader("", "value"); err == nil {
		t.Error("empty header name should be rejected")
	}
}

func TestSanitizeHeader_EmptyValue(t *testing.T) {
	// Empty value is allowed (e.g., clearing a header)
	_, val, err := security.SanitizeHeader("Subject", "")
	if err != nil {
		t.Errorf("empty value should be accepted: %v", err)
	}
	if val != "" {
		t.Errorf("empty value should stay empty, got %q", val)
	}
}

func TestSanitizeHeader_UnicodeValue(t *testing.T) {
	// Unicode in header values should be accepted (UTF-8 MIME encoded downstream)
	_, val, err := security.SanitizeHeader("Subject", "Héllo Wörld")
	if err != nil {
		t.Errorf("unicode header value should be accepted: %v", err)
	}
	if val != "Héllo Wörld" {
		t.Errorf("unicode value should be preserved; got %q", val)
	}
}
