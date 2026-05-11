// Package credential provides credential injection for the Mintkey Egress Proxy plugin.
//
// Inject sets the appropriate outbound headers/query parameters for the
// configured auth scheme and ALWAYS strips the agent's Authorization header.
//
// Source: ADR-0004; ADR-0014.4; vault.proto AuthScheme enum; T-1.6.2.
package credential

import (
	"encoding/base64"
	"fmt"
	"net/http"
)

// AuthScheme mirrors the proto AuthScheme enum (vault.proto).
type AuthScheme int

const (
	AuthSchemeAPIKeyHeader            AuthScheme = 1
	AuthSchemeAPIKeyQuery             AuthScheme = 2
	AuthSchemeBearerToken             AuthScheme = 3
	AuthSchemeBasicAuth               AuthScheme = 4
	AuthSchemeOAuth2ClientCredentials AuthScheme = 5
	AuthSchemeOIDCClientSecret        AuthScheme = 6
	AuthSchemeMTLS                    AuthScheme = 7
)

// Credential holds the plaintext credential and injection metadata.
// The Value bytes MUST be zeroed after use.
type Credential struct {
	AuthScheme AuthScheme
	Value      []byte
	HeaderName string // for AuthSchemeAPIKeyHeader
	QueryParam string // for AuthSchemeAPIKeyQuery
}

// Inject injects the credential into the outbound request and strips the
// agent's Authorization header. Modifies req in place.
//
// For mTLS (AuthScheme=7), returns an error (handled in T-1.6.2 session 2).
func Inject(req *http.Request, cred Credential) error {
	// ALWAYS strip the agent's Authorization header first.
	req.Header.Del("Authorization")

	switch cred.AuthScheme {
	case AuthSchemeAPIKeyHeader:
		name := cred.HeaderName
		if name == "" {
			name = "X-API-Key"
		}
		req.Header.Set(name, string(cred.Value))

	case AuthSchemeAPIKeyQuery:
		param := cred.QueryParam
		if param == "" {
			param = "api_key"
		}
		q := req.URL.Query()
		q.Set(param, string(cred.Value))
		req.URL.RawQuery = q.Encode()

	case AuthSchemeBearerToken:
		req.Header.Set("Authorization", "Bearer "+string(cred.Value))

	case AuthSchemeBasicAuth:
		encoded := base64.StdEncoding.EncodeToString(cred.Value)
		req.Header.Set("Authorization", "Basic "+encoded)

	case AuthSchemeOAuth2ClientCredentials, AuthSchemeOIDCClientSecret:
		req.Header.Set("Authorization", "Bearer "+string(cred.Value))

	case AuthSchemeMTLS:
		return fmt.Errorf("mtls: not implemented in session 1")

	default:
		return fmt.Errorf("unknown auth scheme: %d", cred.AuthScheme)
	}
	return nil
}
