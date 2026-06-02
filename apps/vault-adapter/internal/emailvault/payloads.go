// Package emailvault defines the JSON payload envelopes for the three
// email-proxy credential schemes (ADR-0024). These structs mirror the
// vault.proto AuthScheme enum values 14/15/16:
//
//	AUTH_SCHEME_EMAIL_PASSWORD    = 14
//	AUTH_SCHEME_EMAIL_OAUTH2      = 15
//	AUTH_SCHEME_EMAIL_APP_PASSWORD = 16
//
// Security rules:
//   - Struct fields are zeroed immediately after use by callers.
//   - Structs are never logged; the JSON representation is treated as
//     credential material and follows the same zero/discard rules as
//     AUTH_SCHEME_APPLE_JWT (ADR-0003 / ADR-0024).
//   - Port fields are validated in the range 1..65535 on encode.
//   - Provider must be "gmail" or "outlook" for email_oauth2.
//
// Encoding: JSON, stored encrypted in the vault; decoded on GetCredential.
package emailvault

import (
	"encoding/json"
	"errors"
	"fmt"
)

// validProviders is the closed set of supported OAuth2 providers.
var validProviders = map[string]struct{}{
	"gmail":   {},
	"outlook": {},
}

// EmailPasswordEnvelope is the credential envelope for AUTH_SCHEME_EMAIL_PASSWORD.
// Stored as JSON in the encrypted vault payload.
//
// Field descriptions:
//   - Username: full email address used as IMAP/SMTP login.
//   - Password: plaintext password — NEVER logged, zeroed after use.
//   - IMAPHost: IMAP server hostname (e.g. "imap.gmail.com").
//   - IMAPPort: IMAP port (typically 993 for TLS, 143 for STARTTLS).
//   - SMTPHost: SMTP server hostname (e.g. "smtp.gmail.com").
//   - SMTPPort: SMTP port (typically 587 or 465).
type EmailPasswordEnvelope struct {
	Username string `json:"username"`
	Password string `json:"password"` // SENSITIVE — zeroed after use
	IMAPHost string `json:"imap_host"`
	IMAPPort int    `json:"imap_port"`
	SMTPHost string `json:"smtp_host"`
	SMTPPort int    `json:"smtp_port"`
}

// EmailOAuth2Envelope is the credential envelope for AUTH_SCHEME_EMAIL_OAUTH2.
// Stored as JSON in the encrypted vault payload.
//
// Field descriptions:
//   - Provider:     "gmail" or "outlook".
//   - RefreshToken: long-lived OAuth2 refresh token — NEVER logged, zeroed after use.
//   - EmailAddress: the mailbox email address (informational; used for SMTP From).
type EmailOAuth2Envelope struct {
	Provider     string `json:"provider"`
	RefreshToken string `json:"refresh_token"` // SENSITIVE — zeroed after use
	EmailAddress string `json:"email_address"`
}

// EmailAppPasswordEnvelope is the credential envelope for AUTH_SCHEME_EMAIL_APP_PASSWORD.
// Stored as JSON in the encrypted vault payload.
//
// Field descriptions:
//   - Username:    full email address used as IMAP/SMTP login.
//   - AppPassword: provider-issued app-password (e.g. Google App Password).
//     NEVER logged, zeroed after use.
//   - IMAPHost: IMAP server hostname.
//   - IMAPPort: IMAP port.
//   - SMTPHost: SMTP server hostname.
//   - SMTPPort: SMTP port.
type EmailAppPasswordEnvelope struct {
	Username    string `json:"username"`
	AppPassword string `json:"app_password"` // SENSITIVE — zeroed after use
	IMAPHost    string `json:"imap_host"`
	IMAPPort    int    `json:"imap_port"`
	SMTPHost    string `json:"smtp_host"`
	SMTPPort    int    `json:"smtp_port"`
}

// EncodeEmailPassword validates and JSON-encodes an EmailPasswordEnvelope.
// Returns an error if any required field is empty or if port values are out
// of range [1, 65535].
func EncodeEmailPassword(env EmailPasswordEnvelope) ([]byte, error) {
	if err := validateEmailPassword(env); err != nil {
		return nil, err
	}
	b, err := json.Marshal(env)
	if err != nil {
		return nil, fmt.Errorf("emailvault: encode email_password: %w", err)
	}
	return b, nil
}

// DecodeEmailPassword parses a JSON-encoded EmailPasswordEnvelope.
// Returns an error if the JSON is malformed or required fields are missing.
func DecodeEmailPassword(data []byte) (EmailPasswordEnvelope, error) {
	var env EmailPasswordEnvelope
	if err := json.Unmarshal(data, &env); err != nil {
		return EmailPasswordEnvelope{}, fmt.Errorf("emailvault: decode email_password: %w", err)
	}
	if err := validateEmailPassword(env); err != nil {
		return EmailPasswordEnvelope{}, err
	}
	return env, nil
}

// EncodeEmailOAuth2 validates and JSON-encodes an EmailOAuth2Envelope.
// Returns an error if provider is not "gmail" or "outlook", or if any
// required field is empty.
func EncodeEmailOAuth2(env EmailOAuth2Envelope) ([]byte, error) {
	if err := validateEmailOAuth2(env); err != nil {
		return nil, err
	}
	b, err := json.Marshal(env)
	if err != nil {
		return nil, fmt.Errorf("emailvault: encode email_oauth2: %w", err)
	}
	return b, nil
}

// DecodeEmailOAuth2 parses a JSON-encoded EmailOAuth2Envelope.
// Returns an error if the JSON is malformed or required fields are missing.
func DecodeEmailOAuth2(data []byte) (EmailOAuth2Envelope, error) {
	var env EmailOAuth2Envelope
	if err := json.Unmarshal(data, &env); err != nil {
		return EmailOAuth2Envelope{}, fmt.Errorf("emailvault: decode email_oauth2: %w", err)
	}
	if err := validateEmailOAuth2(env); err != nil {
		return EmailOAuth2Envelope{}, err
	}
	return env, nil
}

// EncodeEmailAppPassword validates and JSON-encodes an EmailAppPasswordEnvelope.
// Returns an error if any required field is empty or port values are out of range.
func EncodeEmailAppPassword(env EmailAppPasswordEnvelope) ([]byte, error) {
	if err := validateEmailAppPassword(env); err != nil {
		return nil, err
	}
	b, err := json.Marshal(env)
	if err != nil {
		return nil, fmt.Errorf("emailvault: encode email_app_password: %w", err)
	}
	return b, nil
}

// DecodeEmailAppPassword parses a JSON-encoded EmailAppPasswordEnvelope.
// Returns an error if the JSON is malformed or required fields are missing.
func DecodeEmailAppPassword(data []byte) (EmailAppPasswordEnvelope, error) {
	var env EmailAppPasswordEnvelope
	if err := json.Unmarshal(data, &env); err != nil {
		return EmailAppPasswordEnvelope{}, fmt.Errorf("emailvault: decode email_app_password: %w", err)
	}
	if err := validateEmailAppPassword(env); err != nil {
		return EmailAppPasswordEnvelope{}, err
	}
	return env, nil
}

// ---------------------------------------------------------------------------
// Validators
// ---------------------------------------------------------------------------

func validatePort(field string, port int) error {
	if port < 1 || port > 65535 {
		return fmt.Errorf("emailvault: %s must be in range 1–65535, got %d", field, port)
	}
	return nil
}

func validateEmailPassword(env EmailPasswordEnvelope) error {
	var errs []error
	if env.Username == "" {
		errs = append(errs, errors.New("emailvault: email_password: username is required"))
	}
	if env.Password == "" {
		errs = append(errs, errors.New("emailvault: email_password: password is required"))
	}
	if env.IMAPHost == "" {
		errs = append(errs, errors.New("emailvault: email_password: imap_host is required"))
	}
	if env.SMTPHost == "" {
		errs = append(errs, errors.New("emailvault: email_password: smtp_host is required"))
	}
	if err := validatePort("imap_port", env.IMAPPort); err != nil {
		errs = append(errs, err)
	}
	if err := validatePort("smtp_port", env.SMTPPort); err != nil {
		errs = append(errs, err)
	}
	return errors.Join(errs...)
}

func validateEmailOAuth2(env EmailOAuth2Envelope) error {
	var errs []error
	if _, ok := validProviders[env.Provider]; !ok {
		errs = append(errs, fmt.Errorf("emailvault: email_oauth2: provider must be \"gmail\" or \"outlook\", got %q", env.Provider))
	}
	if env.RefreshToken == "" {
		errs = append(errs, errors.New("emailvault: email_oauth2: refresh_token is required"))
	}
	if env.EmailAddress == "" {
		errs = append(errs, errors.New("emailvault: email_oauth2: email_address is required"))
	}
	return errors.Join(errs...)
}

func validateEmailAppPassword(env EmailAppPasswordEnvelope) error {
	var errs []error
	if env.Username == "" {
		errs = append(errs, errors.New("emailvault: email_app_password: username is required"))
	}
	if env.AppPassword == "" {
		errs = append(errs, errors.New("emailvault: email_app_password: app_password is required"))
	}
	if env.IMAPHost == "" {
		errs = append(errs, errors.New("emailvault: email_app_password: imap_host is required"))
	}
	if env.SMTPHost == "" {
		errs = append(errs, errors.New("emailvault: email_app_password: smtp_host is required"))
	}
	if err := validatePort("imap_port", env.IMAPPort); err != nil {
		errs = append(errs, err)
	}
	if err := validatePort("smtp_port", env.SMTPPort); err != nil {
		errs = append(errs, err)
	}
	return errors.Join(errs...)
}
