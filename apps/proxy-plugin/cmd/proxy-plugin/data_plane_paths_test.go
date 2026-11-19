package main

import (
	"encoding/json"
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

// TestStrictModeRefusesUnaddressedRequest covers the scenario "an unaddressed
// request is refused in strict mode only": a request that names no service is
// answered 403 {"error":"service not addressed"} before the credential fetch
// with one proxy.aud_mismatch_rejected event, while the permissive handler
// reaches the (unreachable) vault.
func TestStrictModeRefusesUnaddressedRequest_C_12f2e366(t *testing.T) {
	mock := &mockAuditQueue{}
	strict := testHandlerStrictWithAudit(mock)
	permissive := testHandler()
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, nil)
	strict.pubKeys["testkey"] = pub
	permissive.pubKeys["testkey"] = pub

	rw := scopeRequest(t, strict, token, http.MethodGet, "/v1/messages")
	if rw.Code != http.StatusForbidden {
		t.Fatalf("strict unaddressed: status = %d, want %d (body: %s)", rw.Code, http.StatusForbidden, rw.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rw.Body.Bytes(), &body); err != nil {
		t.Fatalf("strict unaddressed: body is not valid JSON: %s", rw.Body.String())
	}
	if got := body["error"]; got != "service not addressed" {
		t.Fatalf("strict unaddressed: error = %v, want %q (body: %s)", got, "service not addressed", rw.Body.String())
	}

	events := mock.captured()
	if len(events) != 1 {
		t.Fatalf("strict unaddressed: audit events = %d, want exactly 1", len(events))
	}
	evt := events[0]
	if evt.EventType != "proxy.aud_mismatch_rejected" {
		t.Errorf("EventType = %q, want proxy.aud_mismatch_rejected", evt.EventType)
	}
	if got := evt.Payload["url_service_id"]; got != "" {
		t.Errorf("Payload.url_service_id = %v, want empty", got)
	}
	if got := evt.Payload["mode"]; got != "strict" {
		t.Errorf("Payload.mode = %v, want strict", got)
	}

	assertScopeReachesVault(t, permissive, token, http.MethodGet, "/v1/messages")
}

// TestStrictModeComparesHeaderAndWireFormWithAudience covers the scenario "the
// header and the wire form are compared with the audience": the header and the
// /v1/call/ wire form of the token's service reach the credential fetch, while
// the wire form of another service answers 403 {"error":"scope mismatch"}.
func TestStrictModeComparesHeaderAndWireFormWithAudience_C_842c06af(t *testing.T) {
	h := testHandlerStrict()
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, nil)
	h.pubKeys["testkey"] = pub

	headerRequest := func(serviceHeader string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodGet, "/v1/messages", nil)
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("X-Mintkey-Service-ID", serviceHeader)
		rw := httptest.NewRecorder()
		h.ServeHTTP(rw, req)
		return rw
	}

	if rw := headerRequest("svc_5ANANANANANANANANANANANANA"); rw.Code != http.StatusBadGateway {
		t.Fatalf("header of the token's service: status = %d, want %d from the unreachable test vault (body: %s)", rw.Code, http.StatusBadGateway, rw.Body.String())
	}

	rw := headerRequest("svc_5VQEXVQEXVQEXVQEXVQEXVQEXV")
	if rw.Code != http.StatusForbidden {
		t.Fatalf("header of another service: status = %d, want %d (body: %s)", rw.Code, http.StatusForbidden, rw.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rw.Body.Bytes(), &body); err != nil {
		t.Fatalf("header of another service: body is not valid JSON: %s", rw.Body.String())
	}
	if got := body["error"]; got != "scope mismatch" {
		t.Fatalf("header of another service: error = %v, want %q (body: %s)", got, "scope mismatch", rw.Body.String())
	}

	assertScopeRefused(t, h, token, http.MethodGet, "/v1/call/svc_5VQEXVQEXVQEXVQEXVQEXVQEXV/x", "scope mismatch")
	assertScopeReachesVault(t, h, token, http.MethodGet, "/v1/call/svc_5ANANANANANANANANANANANANA/x")
}
