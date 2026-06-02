package emailvault_test

import (
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/emailvault"
)

// ---------------------------------------------------------------------------
// EmailPasswordEnvelope
// ---------------------------------------------------------------------------

func TestEncodeDecodeEmailPassword_HappyPath(t *testing.T) {
	env := emailvault.EmailPasswordEnvelope{
		Username: "alice@example.com",
		Password: "s3cr3t",
		IMAPHost: "imap.example.com",
		IMAPPort: 993,
		SMTPHost: "smtp.example.com",
		SMTPPort: 587,
	}
	data, err := emailvault.EncodeEmailPassword(env)
	if err != nil {
		t.Fatalf("EncodeEmailPassword() unexpected error: %v", err)
	}
	if len(data) == 0 {
		t.Fatal("EncodeEmailPassword() returned empty bytes")
	}

	got, err := emailvault.DecodeEmailPassword(data)
	if err != nil {
		t.Fatalf("DecodeEmailPassword() unexpected error: %v", err)
	}
	if got.Username != env.Username {
		t.Errorf("Username: got %q, want %q", got.Username, env.Username)
	}
	if got.Password != env.Password {
		t.Errorf("Password: got %q, want %q", got.Password, env.Password)
	}
	if got.IMAPHost != env.IMAPHost {
		t.Errorf("IMAPHost: got %q, want %q", got.IMAPHost, env.IMAPHost)
	}
	if got.IMAPPort != env.IMAPPort {
		t.Errorf("IMAPPort: got %d, want %d", got.IMAPPort, env.IMAPPort)
	}
	if got.SMTPHost != env.SMTPHost {
		t.Errorf("SMTPHost: got %q, want %q", got.SMTPHost, env.SMTPHost)
	}
	if got.SMTPPort != env.SMTPPort {
		t.Errorf("SMTPPort: got %d, want %d", got.SMTPPort, env.SMTPPort)
	}
}

func TestEncodeEmailPassword_MissingUsername(t *testing.T) {
	env := emailvault.EmailPasswordEnvelope{
		Password: "s3cr3t",
		IMAPHost: "imap.example.com",
		IMAPPort: 993,
		SMTPHost: "smtp.example.com",
		SMTPPort: 587,
	}
	_, err := emailvault.EncodeEmailPassword(env)
	if err == nil {
		t.Fatal("expected error for missing username, got nil")
	}
	if !strings.Contains(err.Error(), "username") {
		t.Errorf("error should mention username field, got: %v", err)
	}
}

func TestEncodeEmailPassword_MissingPassword(t *testing.T) {
	env := emailvault.EmailPasswordEnvelope{
		Username: "alice@example.com",
		IMAPHost: "imap.example.com",
		IMAPPort: 993,
		SMTPHost: "smtp.example.com",
		SMTPPort: 587,
	}
	_, err := emailvault.EncodeEmailPassword(env)
	if err == nil {
		t.Fatal("expected error for missing password, got nil")
	}
}

func TestEncodeEmailPassword_InvalidIMAPPort(t *testing.T) {
	env := emailvault.EmailPasswordEnvelope{
		Username: "alice@example.com",
		Password: "s3cr3t",
		IMAPHost: "imap.example.com",
		IMAPPort: 0, // invalid
		SMTPHost: "smtp.example.com",
		SMTPPort: 587,
	}
	_, err := emailvault.EncodeEmailPassword(env)
	if err == nil {
		t.Fatal("expected error for invalid imap_port=0, got nil")
	}
	if !strings.Contains(err.Error(), "imap_port") {
		t.Errorf("error should mention imap_port, got: %v", err)
	}
}

func TestEncodeEmailPassword_InvalidSMTPPort(t *testing.T) {
	env := emailvault.EmailPasswordEnvelope{
		Username: "alice@example.com",
		Password: "s3cr3t",
		IMAPHost: "imap.example.com",
		IMAPPort: 993,
		SMTPHost: "smtp.example.com",
		SMTPPort: 65536, // invalid
	}
	_, err := emailvault.EncodeEmailPassword(env)
	if err == nil {
		t.Fatal("expected error for invalid smtp_port=65536, got nil")
	}
	if !strings.Contains(err.Error(), "smtp_port") {
		t.Errorf("error should mention smtp_port, got: %v", err)
	}
}

func TestDecodeEmailPassword_MalformedJSON(t *testing.T) {
	_, err := emailvault.DecodeEmailPassword([]byte("{invalid json"))
	if err == nil {
		t.Fatal("expected error for malformed JSON, got nil")
	}
}

func TestDecodeEmailPassword_MissingRequiredFields(t *testing.T) {
	// Valid JSON but missing all required fields.
	_, err := emailvault.DecodeEmailPassword([]byte(`{}`))
	if err == nil {
		t.Fatal("expected error for missing required fields, got nil")
	}
}

// ---------------------------------------------------------------------------
// EmailOAuth2Envelope
// ---------------------------------------------------------------------------

func TestEncodeDecodeEmailOAuth2_Gmail(t *testing.T) {
	env := emailvault.EmailOAuth2Envelope{
		Provider:     "gmail",
		RefreshToken: "1//0gRefreshTokenValue",
		EmailAddress: "alice@gmail.com",
	}
	data, err := emailvault.EncodeEmailOAuth2(env)
	if err != nil {
		t.Fatalf("EncodeEmailOAuth2() unexpected error: %v", err)
	}

	got, err := emailvault.DecodeEmailOAuth2(data)
	if err != nil {
		t.Fatalf("DecodeEmailOAuth2() unexpected error: %v", err)
	}
	if got.Provider != "gmail" {
		t.Errorf("Provider: got %q, want %q", got.Provider, "gmail")
	}
	if got.RefreshToken != env.RefreshToken {
		t.Errorf("RefreshToken mismatch")
	}
	if got.EmailAddress != env.EmailAddress {
		t.Errorf("EmailAddress: got %q, want %q", got.EmailAddress, env.EmailAddress)
	}
}

func TestEncodeDecodeEmailOAuth2_Outlook(t *testing.T) {
	env := emailvault.EmailOAuth2Envelope{
		Provider:     "outlook",
		RefreshToken: "M.C512_BAY.0.U.-CdRefreshTokenValue",
		EmailAddress: "bob@outlook.com",
	}
	data, err := emailvault.EncodeEmailOAuth2(env)
	if err != nil {
		t.Fatalf("EncodeEmailOAuth2() unexpected error: %v", err)
	}
	got, err := emailvault.DecodeEmailOAuth2(data)
	if err != nil {
		t.Fatalf("DecodeEmailOAuth2() unexpected error: %v", err)
	}
	if got.Provider != "outlook" {
		t.Errorf("Provider: got %q, want %q", got.Provider, "outlook")
	}
}

func TestEncodeEmailOAuth2_InvalidProvider(t *testing.T) {
	env := emailvault.EmailOAuth2Envelope{
		Provider:     "yahoo", // unsupported
		RefreshToken: "tok",
		EmailAddress: "alice@yahoo.com",
	}
	_, err := emailvault.EncodeEmailOAuth2(env)
	if err == nil {
		t.Fatal("expected error for unsupported provider, got nil")
	}
	if !strings.Contains(err.Error(), "provider") {
		t.Errorf("error should mention provider, got: %v", err)
	}
}

func TestEncodeEmailOAuth2_EmptyRefreshToken(t *testing.T) {
	env := emailvault.EmailOAuth2Envelope{
		Provider:     "gmail",
		RefreshToken: "",
		EmailAddress: "alice@gmail.com",
	}
	_, err := emailvault.EncodeEmailOAuth2(env)
	if err == nil {
		t.Fatal("expected error for empty refresh_token, got nil")
	}
}

func TestEncodeEmailOAuth2_EmptyEmailAddress(t *testing.T) {
	env := emailvault.EmailOAuth2Envelope{
		Provider:     "outlook",
		RefreshToken: "tok",
		EmailAddress: "",
	}
	_, err := emailvault.EncodeEmailOAuth2(env)
	if err == nil {
		t.Fatal("expected error for empty email_address, got nil")
	}
}

func TestDecodeEmailOAuth2_MalformedJSON(t *testing.T) {
	_, err := emailvault.DecodeEmailOAuth2([]byte("not-json"))
	if err == nil {
		t.Fatal("expected error for malformed JSON, got nil")
	}
}

// ---------------------------------------------------------------------------
// EmailAppPasswordEnvelope
// ---------------------------------------------------------------------------

func TestEncodeDecodeEmailAppPassword_HappyPath(t *testing.T) {
	env := emailvault.EmailAppPasswordEnvelope{
		Username:    "alice@example.com",
		AppPassword: "xxxx yyyy zzzz wwww",
		IMAPHost:    "imap.example.com",
		IMAPPort:    993,
		SMTPHost:    "smtp.example.com",
		SMTPPort:    465,
	}
	data, err := emailvault.EncodeEmailAppPassword(env)
	if err != nil {
		t.Fatalf("EncodeEmailAppPassword() unexpected error: %v", err)
	}

	got, err := emailvault.DecodeEmailAppPassword(data)
	if err != nil {
		t.Fatalf("DecodeEmailAppPassword() unexpected error: %v", err)
	}
	if got.Username != env.Username {
		t.Errorf("Username: got %q, want %q", got.Username, env.Username)
	}
	if got.AppPassword != env.AppPassword {
		t.Errorf("AppPassword mismatch")
	}
	if got.IMAPPort != env.IMAPPort {
		t.Errorf("IMAPPort: got %d, want %d", got.IMAPPort, env.IMAPPort)
	}
}

func TestEncodeEmailAppPassword_MissingAppPassword(t *testing.T) {
	env := emailvault.EmailAppPasswordEnvelope{
		Username: "alice@example.com",
		IMAPHost: "imap.example.com",
		IMAPPort: 993,
		SMTPHost: "smtp.example.com",
		SMTPPort: 587,
	}
	_, err := emailvault.EncodeEmailAppPassword(env)
	if err == nil {
		t.Fatal("expected error for missing app_password, got nil")
	}
}

func TestEncodeEmailAppPassword_InvalidPort(t *testing.T) {
	env := emailvault.EmailAppPasswordEnvelope{
		Username:    "alice@example.com",
		AppPassword: "xxxx yyyy",
		IMAPHost:    "imap.example.com",
		IMAPPort:    -1, // invalid
		SMTPHost:    "smtp.example.com",
		SMTPPort:    587,
	}
	_, err := emailvault.EncodeEmailAppPassword(env)
	if err == nil {
		t.Fatal("expected error for invalid imap_port=-1, got nil")
	}
}

func TestDecodeEmailAppPassword_MalformedJSON(t *testing.T) {
	_, err := emailvault.DecodeEmailAppPassword([]byte("{}bad"))
	if err == nil {
		t.Fatal("expected error for malformed JSON, got nil")
	}
}

// ---------------------------------------------------------------------------
// Port boundary tests
// ---------------------------------------------------------------------------

func TestPortBoundary_Min(t *testing.T) {
	env := emailvault.EmailPasswordEnvelope{
		Username: "u@example.com",
		Password: "p",
		IMAPHost: "imap.example.com",
		IMAPPort: 1,
		SMTPHost: "smtp.example.com",
		SMTPPort: 1,
	}
	if _, err := emailvault.EncodeEmailPassword(env); err != nil {
		t.Errorf("port=1 should be valid, got error: %v", err)
	}
}

func TestPortBoundary_Max(t *testing.T) {
	env := emailvault.EmailPasswordEnvelope{
		Username: "u@example.com",
		Password: "p",
		IMAPHost: "imap.example.com",
		IMAPPort: 65535,
		SMTPHost: "smtp.example.com",
		SMTPPort: 65535,
	}
	if _, err := emailvault.EncodeEmailPassword(env); err != nil {
		t.Errorf("port=65535 should be valid, got error: %v", err)
	}
}
