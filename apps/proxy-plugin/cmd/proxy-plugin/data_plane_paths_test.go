package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
)

// TestUpstreamPathStripsCallPrefixOfTheTokensService covers the scenario "the
// call prefix is removed for the token's service only": both the UUID and the
// svc_ wire form of the token's service are removed from /v1/call/<seg>, a
// prefix of another service is kept, and the pre-existing /<serviceID> rule
// still applies.
func TestUpstreamPathStripsCallPrefixOfTheTokensService_C_186f98fb(t *testing.T) {
	cases := []struct {
		path string
		want string
	}{
		{"/v1/call/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/v1/messages", "/v1/messages"},
		{"/v1/call/svc_5ANANANANANANANANANANANANA/v1/messages", "/v1/messages"},
		{"/v1/call/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "/"},
		{"/v1/call/svc_5VQEXVQEXVQEXVQEXVQEXVQEXV/v1/messages", "/v1/call/svc_5VQEXVQEXVQEXVQEXVQEXVQEXV/v1/messages"},
		{"/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/v1/messages", "/v1/messages"},
	}
	for _, tc := range cases {
		if got := upstreamPath(tc.path, testSvcUUIDA); got != tc.want {
			t.Errorf("upstreamPath(%q, %q) = %q, want %q", tc.path, testSvcUUIDA, got, tc.want)
		}
	}
}

// TestDigestDirectorForwardsBarePathWithoutRoutingHeaders covers the scenario
// "the upstream receives the bare path under its base path, without routing
// headers": a digest call addressed with the svc_ wire form reaches the
// upstream as /base/v1/messages and neither routing header survives.
func TestDigestDirectorForwardsBarePathWithoutRoutingHeaders_C_a40d5e55(t *testing.T) {
	var gotPath, gotServiceHeader, gotTenantHeader string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotServiceHeader = r.Header.Get("X-Mintkey-Service-ID")
		gotTenantHeader = r.Header.Get("X-Mintkey-Tenant-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	h := testHandler()
	credResp := &vault.GetCredentialResponse{
		AuthScheme: int32(credential.AuthSchemeHTTPDigest),
		Plaintext:  []byte(`{"public_key":"pk-test","private_key":"sk-test"}`),
		TargetURL:  upstream.URL + "/base",
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/call/svc_5ANANANANANANANANANANANANA/v1/messages", nil)
	req.Header.Set("X-Mintkey-Service-ID", testSvcUUIDA)
	req.Header.Set("X-Mintkey-Tenant-ID", "tenant-test-uuid-0001")
	rw := httptest.NewRecorder()

	h.handleHTTPDigest(rw, req, credResp, "tenant-test-uuid-0001", testSvcUUIDA, "agent_test", time.Now())

	if rw.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d (body: %s)", rw.Code, http.StatusOK, rw.Body.String())
	}
	if gotPath != "/base/v1/messages" {
		t.Errorf("upstream path = %q, want %q", gotPath, "/base/v1/messages")
	}
	if gotServiceHeader != "" {
		t.Errorf("upstream X-Mintkey-Service-ID = %q, want empty", gotServiceHeader)
	}
	if gotTenantHeader != "" {
		t.Errorf("upstream X-Mintkey-Tenant-ID = %q, want empty", gotTenantHeader)
	}
}

// TestPathPrefixClaimMatchesCallForm covers the scenario "a path_prefix claim
// matches the call form": the scope check strips /v1/call/<svc wire form>
// before matching, so the request reaches the (unreachable) vault and answers
// 502 rather than 403.
func TestPathPrefixClaimMatchesCallForm_C_c6932f9e(t *testing.T) {
	h := testHandler()
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, map[string]any{"path_prefix": "/v1/messages"})
	h.pubKeys["testkey"] = pub

	assertScopeReachesVault(t, h, token, http.MethodGet, "/v1/call/svc_5ANANANANANANANANANANANANA/v1/messages/x")
}
