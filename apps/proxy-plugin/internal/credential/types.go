// Package credential provides credential injection for the Mintkey Egress Proxy plugin.
//
// This file defines structured credential types for complex auth schemes
// that require multi-field payloads (e.g., OAuth2 Password Grant).
package credential

// OAuth2PasswordGrantCredential is the JSON structure stored in the Vault
// for auth_scheme=8 credentials. The Proxy Plugin parses this from the
// GetCredential response value to perform token exchange.
type OAuth2PasswordGrantCredential struct {
	TokenURL            string            `json:"token_url"`
	CredentialFields    map[string]string `json:"credential_fields"`
	TokenResponsePath   string            `json:"token_response_path"`
	TokenRequestHeaders map[string]string `json:"token_request_headers,omitempty"`
	// ExchangeTimeoutSeconds is the whole-request timeout for the token exchange
	// HTTP call. Default (0 or missing) = 10s; bounds [1, 120].
	// The Go side defensively clamps: ≤0 → 10, >120 → 120.
	ExchangeTimeoutSeconds int `json:"exchange_timeout_seconds,omitempty"`
}
