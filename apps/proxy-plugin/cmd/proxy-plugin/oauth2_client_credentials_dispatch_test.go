package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
)

// TestIsClientCredentialsExchangeShaped verifies the dispatch predicate: only a
// JSON payload with a non-empty token_url is exchange-shaped; anything else falls
// through to the generic (pre-fetched bearer) injector.
func TestIsClientCredentialsExchangeShaped(t *testing.T) {
	cases := []struct {
		name    string
		payload string
		want    bool
	}{
		{"json with token_url", `{"token_url":"https://cloud.mongodb.com/api/oauth/token","client_id":"c","client_secret":"s"}`, true},
		{"json without token_url", `{"client_id":"c","client_secret":"s"}`, false},
		{"json empty token_url", `{"token_url":"","client_id":"c"}`, false},
		{"opaque pre-fetched bearer", "ya29.some-opaque-bearer-token", false},
		{"empty", "", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := isClientCredentialsExchangeShaped([]byte(tc.payload)); got != tc.want {
				t.Errorf("isClientCredentialsExchangeShaped(%q) = %v, want %v", tc.payload, got, tc.want)
			}
		})
	}
}

// TestHandleOAuth2ClientCredentials_InjectsExchangedBearer routes an
// exchange-shaped scheme-5 credential through the client-credentials handler and
// asserts the upstream receives Authorization: Bearer <exchanged-token> and never
// sees the client secret.
func TestHandleOAuth2ClientCredentials_InjectsExchangedBearer(t *testing.T) {
	const (
		clientSecret   = "CLIENT-SECRET-MUST-NOT-LEAK"
		exchangedToken = "exchanged-cc-bearer-XYZ"
	)

	// Fake token endpoint: returns the exchanged access token.
	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"access_token":"` + exchangedToken + `","expires_in":3600}`))
	}))
	defer tokenSrv.Close()

	// Fake upstream: captures the Authorization header it receives.
	var gotAuth string
	upstreamSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
	}))
	defer upstreamSrv.Close()

	h := testHandler()
	// AllowPrivate: the fake token endpoint is on loopback, which the default
	// SSRF guard would block. The exchange logic under test is unchanged.
	h.tokenExchanger = credential.NewTokenExchangerAllowPrivate()
	h.tokenCache = cache.NewTokenCache()

	credPayload, err := json.Marshal(credential.OAuth2ClientCredentialsCredential{
		TokenURL:     tokenSrv.URL + "/api/oauth/token",
		ClientID:     "my-client-id",
		ClientSecret: clientSecret,
	})
	if err != nil {
		t.Fatalf("marshal credential: %v", err)
	}

	// Sanity: the payload must be routed to the exchange path.
	if !isClientCredentialsExchangeShaped(credPayload) {
		t.Fatal("payload should be exchange-shaped")
	}

	credResp := &vault.GetCredentialResponse{
		AuthScheme: int32(credential.AuthSchemeOAuth2ClientCredentials),
		Plaintext:  credPayload,
		TargetURL:  upstreamSrv.URL,
	}

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rw := httptest.NewRecorder()
	h.handleOAuth2ClientCredentials(rw, req, credResp, "tenant-test-uuid-0001", testSvcUUIDA, "agent_cc_test", time.Now())

	if rw.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rw.Code)
	}
	if gotAuth != "Bearer "+exchangedToken {
		t.Errorf("upstream Authorization = %q, want %q", gotAuth, "Bearer "+exchangedToken)
	}
	if strings.Contains(gotAuth, clientSecret) {
		t.Fatal("client secret leaked into upstream Authorization header")
	}
}
