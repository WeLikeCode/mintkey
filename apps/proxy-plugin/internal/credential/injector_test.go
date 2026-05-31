package credential_test

import (
	"encoding/base64"
	"net/http"
	"net/url"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
)

func makeRequest(method, rawURL string) *http.Request {
	u, _ := url.Parse(rawURL)
	return &http.Request{
		Method: method,
		URL:    u,
		Header: http.Header{
			"Authorization": []string{"Bearer agent-jwt-token"},
		},
	}
}

func assert(t *testing.T, cond bool) {
	t.Helper()
	if !cond {
		t.Fatal("assertion failed")
	}
}

func TestInject_APIKeyHeader(t *testing.T) {
	req := makeRequest("GET", "https://api.example.com/v1/data")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeAPIKeyHeader,
		Value:      []byte("sk_live_key123"),
		HeaderName: "X-API-Key",
	}
	err := credential.Inject(req, cred)
	assert(t, err == nil)
	assert(t, req.Header.Get("X-API-Key") == "sk_live_key123")
	assert(t, req.Header.Get("Authorization") == "") // stripped
}

func TestInject_APIKeyQuery(t *testing.T) {
	req := makeRequest("GET", "https://api.example.com/v1/data")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeAPIKeyQuery,
		Value:      []byte("key123"),
		QueryParam: "api_key",
	}
	err := credential.Inject(req, cred)
	assert(t, err == nil)
	assert(t, req.URL.Query().Get("api_key") == "key123")
	assert(t, req.Header.Get("Authorization") == "")
}

func TestInject_BearerToken(t *testing.T) {
	req := makeRequest("GET", "https://api.example.com/v1/data")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeBearerToken,
		Value:      []byte("token_abc"),
	}
	err := credential.Inject(req, cred)
	assert(t, err == nil)
	assert(t, req.Header.Get("Authorization") == "Bearer token_abc")
}

func TestInject_BasicAuth(t *testing.T) {
	// Value format: "username:password"
	req := makeRequest("GET", "https://api.example.com/v1/data")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeBasicAuth,
		Value:      []byte("user123:pass456"),
	}
	err := credential.Inject(req, cred)
	assert(t, err == nil)
	expected := "Basic " + base64.StdEncoding.EncodeToString([]byte("user123:pass456"))
	assert(t, req.Header.Get("Authorization") == expected)
}

func TestInject_OAuth2ClientCredentials(t *testing.T) {
	// Value is access_token directly
	req := makeRequest("GET", "https://api.example.com/v1/data")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeOAuth2ClientCredentials,
		Value:      []byte("access_token_xyz"),
	}
	err := credential.Inject(req, cred)
	assert(t, err == nil)
	assert(t, req.Header.Get("Authorization") == "Bearer access_token_xyz")
}

func TestInject_OAuth2PasswordGrant(t *testing.T) {
	// Value is the already-exchanged bearer token
	req := makeRequest("GET", "https://api.example.com/v1/data")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeOAuth2PasswordGrant,
		Value:      []byte("exchanged_jwt_token_xyz"),
	}
	err := credential.Inject(req, cred)
	assert(t, err == nil)
	assert(t, req.Header.Get("Authorization") == "Bearer exchanged_jwt_token_xyz")
}

func TestInject_AppleJWT(t *testing.T) {
	// apple_jwt: Vault Adapter has already generated the ES256 JWT and placed it
	// in Value. Proxy treats it opaquely — same Authorization: Bearer header as
	// bearer_token. No JWT generation or decode happens here.
	req := makeRequest("GET", "https://api.example.com/v1/data")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeAppleJWT,
		Value:      []byte("eyJhbGciOiJFUzI1NiJ9.apple_payload.sig"),
	}
	err := credential.Inject(req, cred)
	assert(t, err == nil)
	assert(t, req.Header.Get("Authorization") == "Bearer eyJhbGciOiJFUzI1NiJ9.apple_payload.sig")
}

func TestInject_StripAgentAuthAlways(t *testing.T) {
	// Even for api_key_header, the original Authorization must be gone
	req := makeRequest("GET", "https://api.example.com/v1/data")
	req.Header.Set("Authorization", "Bearer original-agent-jwt")
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeAPIKeyHeader,
		Value:      []byte("backend_key"),
		HeaderName: "X-API-Key",
	}
	credential.Inject(req, cred)
	assert(t, req.Header.Get("Authorization") == "")
}
