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

// OAuth2ClientCredentialsCredential is the JSON structure stored in the Vault
// for auth_scheme=5 (oauth2_client_credentials) credentials whose payload is a
// live-exchange envelope. The Proxy Plugin parses this from the GetCredential
// response value to perform an OAuth 2.0 client-credentials token exchange
// (form body grant_type=client_credentials + HTTP Basic client_id:client_secret).
type OAuth2ClientCredentialsCredential struct {
	TokenURL     string `json:"token_url"`
	ClientID     string `json:"client_id"`
	ClientSecret string `json:"client_secret"`
	// Scope is optional space-delimited scopes; omitted from the request when empty.
	Scope string `json:"scope,omitempty"`
	// Audience is the optional OAuth2 token-request audience (e.g. the Auth0
	// Management API identifier https://YOUR_TENANT.auth0.com/api/v2/).
	// Omitted from the token-request form body when empty.
	Audience string `json:"audience,omitempty"`
	// TokenResponsePath is the JSONPath to the access token; default "$.access_token".
	TokenResponsePath string `json:"token_response_path,omitempty"`
	// ExchangeTimeoutSeconds is the whole-request timeout for the token exchange
	// HTTP call. Default (0 or missing) = 10s; bounds [1, 120].
	// The Go side defensively clamps: ≤0 → 10, >120 → 120.
	ExchangeTimeoutSeconds int `json:"exchange_timeout_seconds,omitempty"`
}

// HTTPDigestCredential is the JSON structure stored in the Vault for
// auth_scheme=18 (http_digest) credentials. The Proxy Plugin parses this from
// the GetCredential response value and uses PublicKey as the RFC 2617 username
// and PrivateKey as the password for a per-request Digest challenge-response
// (e.g. MongoDB Atlas Programmatic API Keys).
type HTTPDigestCredential struct {
	PublicKey  string `json:"public_key"`  // RFC 2617 username
	PrivateKey string `json:"private_key"` // RFC 2617 password
}
