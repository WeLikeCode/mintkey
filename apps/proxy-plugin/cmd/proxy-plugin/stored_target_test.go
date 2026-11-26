package main

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/classicalkey"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/proto"
)

// The test values of the scenarios, built from parts so that no secret-shaped
// literal is written in this file: <tokenA> is "opaque-token-0123456789",
// <tokenB> is "exchanged-token-ABCDEF123" and the classical key is
// "mk_svckey_test".
var (
	storedTargetTokenA       = "opaque-" + "token-" + "0123456789"
	storedTargetTokenB       = "exchanged-" + "token-" + "ABCDEF" + "123"
	storedTargetClassicalKey = "mk_" + "svckey_" + "test"
)

// testRoundTripper adapts a function to http.RoundTripper.
type testRoundTripper func(*http.Request) (*http.Response, error)

func (f testRoundTripper) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

// fakeVaultServer answers GetCredential with a clone of one response.
type fakeVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	resp *vaultv1.GetCredentialResponse
}

func (f *fakeVaultServer) GetCredential(context.Context, *vaultv1.GetCredentialRequest) (*vaultv1.GetCredentialResponse, error) {
	if f.resp == nil {
		return nil, nil
	}
	return proto.Clone(f.resp).(*vaultv1.GetCredentialResponse), nil
}

// startFakeVault serves GetCredential on 127.0.0.1:0 and returns a client for it.
func startFakeVault(t *testing.T, resp *vaultv1.GetCredentialResponse) *vault.Client {
	t.Helper()

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen for the fake vault: %v", err)
	}
	srv := grpc.NewServer()
	vaultv1.RegisterVaultAdapterServer(srv, &fakeVaultServer{resp: resp})
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(srv.Stop)

	client := vault.NewClient(lis.Addr().String(), "", "")
	t.Cleanup(func() { _ = client.Close() })
	return client
}

// countingUpstream records the number of requests it received, the headers of
// the last one, and whether any request carried X-Mintkey-Target.
func countingUpstream(t *testing.T) (*httptest.Server, func() (int, http.Header, bool)) {
	t.Helper()

	var mu sync.Mutex
	var count int
	var last http.Header
	var sawTargetHeader bool

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		count++
		last = r.Header.Clone()
		if _, ok := r.Header["X-Mintkey-Target"]; ok {
			sawTargetHeader = true
		}
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	snapshot := func() (int, http.Header, bool) {
		mu.Lock()
		defer mu.Unlock()
		var headers http.Header
		if last != nil {
			headers = last.Clone()
		}
		return count, headers, sawTargetHeader
	}
	return srv, snapshot
}

// bearerCredential builds the bearer credential of the generic flow.
func bearerCredential(target, value string) *vaultv1.GetCredentialResponse {
	return &vaultv1.GetCredentialResponse{
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte(value),
		TargetUrl:  target,
	}
}

// callGenericFlow runs the generic injector of ServeHTTP.
func callGenericFlow(t *testing.T, h *proxyHandler, cred *vaultv1.GetCredentialResponse, targetHeader string) *httptest.ResponseRecorder {
	t.Helper()

	h.vaultClient = startFakeVault(t, cred)
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, nil)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	if targetHeader != "" {
		req.Header.Set("X-Mintkey-Target", targetHeader)
	}
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	return rw
}

// callClassicalFlow runs the classical service key path of ServeHTTP.
func callClassicalFlow(t *testing.T, h *proxyHandler, cred *vaultv1.GetCredentialResponse, targetHeader string) *httptest.ResponseRecorder {
	t.Helper()

	broker := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"api_key_id":      "k1",
			"agent_id":        "agent_ck",
			"service_id":      testSvcUUIDA,
			"allowed_actions": []string{"call"},
		})
	}))
	t.Cleanup(broker.Close)
	h.ckHandler = classicalkey.NewHandler(classicalkey.Config{BrokerURL: broker.URL, CacheTTL: time.Minute})
	h.vaultClient = startFakeVault(t, cred)

	req := httptest.NewRequest(http.MethodGet, "/"+testSvcUUIDA+"/echo", nil)
	req.Header.Set("Authorization", "Bearer "+storedTargetClassicalKey)
	req.Header.Set("X-Mintkey-Service-ID", testSvcUUIDA)
	req.Header.Set("X-Mintkey-Tenant-ID", "tenant-test-uuid-0001")
	if targetHeader != "" {
		req.Header.Set("X-Mintkey-Target", targetHeader)
	}
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	return rw
}

// callDigestFlow runs handleHTTPDigest directly.
func callDigestFlow(t *testing.T, h *proxyHandler, target, targetHeader string) *httptest.ResponseRecorder {
	t.Helper()

	cred := &vault.GetCredentialResponse{
		AuthScheme: int32(credential.AuthSchemeHTTPDigest),
		Plaintext:  []byte(`{"public_key":"pk-test","private_key":"sk-test"}`),
		TargetURL:  target,
	}
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil)
	if targetHeader != "" {
		req.Header.Set("X-Mintkey-Target", targetHeader)
	}
	rw := httptest.NewRecorder()
	h.handleHTTPDigest(rw, req, cred, "tenant-test-uuid-0001", testSvcUUIDA, "agent_digest", time.Now())
	return rw
}

// callClientCredentialsFlow runs handleOAuth2ClientCredentials directly.
func callClientCredentialsFlow(t *testing.T, h *proxyHandler, target, targetHeader, tokenURL string) *httptest.ResponseRecorder {
	t.Helper()

	h.tokenExchanger = credential.NewTokenExchangerAllowPrivate()
	h.tokenCache = cache.NewTokenCache()
	payload, err := json.Marshal(credential.OAuth2ClientCredentialsCredential{
		TokenURL:     tokenURL + "/token",
		ClientID:     "client-id",
		ClientSecret: "client-" + "secret-" + "value",
	})
	if err != nil {
		t.Fatalf("marshal the client-credentials payload: %v", err)
	}
	cred := &vault.GetCredentialResponse{
		AuthScheme: int32(credential.AuthSchemeOAuth2ClientCredentials),
		Plaintext:  payload,
		TargetURL:  target,
	}
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil)
	if targetHeader != "" {
		req.Header.Set("X-Mintkey-Target", targetHeader)
	}
	rw := httptest.NewRecorder()
	h.handleOAuth2ClientCredentials(rw, req, cred, "tenant-test-uuid-0001", testSvcUUIDA, "agent_cc", time.Now())
	return rw
}

// callPasswordGrantFlow runs handleOAuth2PasswordGrant directly.
func callPasswordGrantFlow(t *testing.T, h *proxyHandler, target, targetHeader, tokenURL string) *httptest.ResponseRecorder {
	t.Helper()

	h.tokenExchanger = credential.NewTokenExchangerAllowPrivate()
	h.tokenCache = cache.NewTokenCache()
	payload, err := json.Marshal(credential.OAuth2PasswordGrantCredential{
		TokenURL: tokenURL + "/token?grant_type=password",
		CredentialFields: map[string]string{
			"username": "testuser",
			"password": "test-" + "password-" + "value",
		},
		TokenResponsePath: "$.token",
	})
	if err != nil {
		t.Fatalf("marshal the password-grant payload: %v", err)
	}
	cred := &vault.GetCredentialResponse{
		AuthScheme: int32(credential.AuthSchemeOAuth2PasswordGrant),
		Plaintext:  payload,
		TargetURL:  target,
	}
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil)
	if targetHeader != "" {
		req.Header.Set("X-Mintkey-Target", targetHeader)
	}
	rw := httptest.NewRecorder()
	h.handleOAuth2PasswordGrant(rw, req, cred, "tenant-test-uuid-0001", testSvcUUIDA, "agent_pg", time.Now())
	return rw
}

// callFlows runs the five flows against one stored-target value and returns
// their recorders: generic, classical key, digest, client credentials and
// password grant.
func callFlows(t *testing.T, h *proxyHandler, targetFor, targetHeader string) []*httptest.ResponseRecorder {
	t.Helper()

	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token": storedTargetTokenB,
			"token":        storedTargetTokenB,
			"expires_in":   3600,
		})
	}))
	t.Cleanup(tokenSrv.Close)

	return []*httptest.ResponseRecorder{
		callGenericFlow(t, h, bearerCredential(targetFor, storedTargetTokenA), targetHeader),
		callClassicalFlow(t, h, &vaultv1.GetCredentialResponse{
			AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
			Value:      []byte("classical-" + "secret-" + "value"),
			HeaderName: "X-Api-Key",
			TargetUrl:  targetFor,
		}, targetHeader),
		callDigestFlow(t, h, targetFor, targetHeader),
		callClientCredentialsFlow(t, h, targetFor, targetHeader, tokenSrv.URL),
		callPasswordGrantFlow(t, h, targetFor, targetHeader, tokenSrv.URL),
	}
}

// TestStoredTargetWinsInEveryFlow covers the scenario "the stored target wins
// over the header and the default": every flow goes to the stored target only,
// ignores X-Mintkey-Target and cfg.DefaultTarget, and forwards no
// X-Mintkey-Target header. Its last part also pins that the header and the
// default do not rescue a credential whose stored target is empty.
func TestStoredTargetWinsInEveryFlow_C_18de099e_C_e1860d3e(t *testing.T) {
	h := testHandler()
	upstreamA, statsA := countingUpstream(t)
	upstreamB, statsB := countingUpstream(t)
	upstreamC, statsC := countingUpstream(t)
	h.cfg.DefaultTarget = upstreamC.URL

	recorders := callFlows(t, h, upstreamA.URL, upstreamB.URL)

	for flow, rw := range recorders {
		if rw.Code != http.StatusOK {
			t.Fatalf("flow %d: status = %d, want %d (body: %s)", flow, rw.Code, http.StatusOK, rw.Body.String())
		}
	}

	countA, _, sawTargetHeader := statsA()
	if countA != 5 {
		t.Fatalf("the stored target received %d requests, want 5 (one per flow)", countA)
	}
	if sawTargetHeader {
		t.Fatal("an upstream request carried X-Mintkey-Target; the header must not reach the upstream")
	}
	if got, _, _ := statsB(); got != 0 {
		t.Fatalf("the header target received %d requests, want 0", got)
	}
	if got, _, _ := statsC(); got != 0 {
		t.Fatalf("the default target received %d requests, want 0", got)
	}

	// The same request with an empty stored target is refused, even though the
	// header and the default name running upstreams.
	missing := callGenericFlow(t, h, bearerCredential("", storedTargetTokenA), upstreamB.URL)
	if missing.Code != http.StatusBadGateway {
		t.Fatalf("empty stored target: status = %d, want %d (body: %s)", missing.Code, http.StatusBadGateway, missing.Body.String())
	}
	if body := strings.TrimSpace(missing.Body.String()); body != "bad gateway: no target URL stored for this credential" {
		t.Fatalf("empty stored target: body = %q, want %q", body, "bad gateway: no target URL stored for this credential")
	}
	if got, _, _ := statsB(); got != 0 {
		t.Fatalf("empty stored target: the header target received %d requests, want 0", got)
	}
}

// TestMissingStoredTargetIsRefusedInEveryFlow covers the scenario "a credential
// with no stored target is refused": each of the five flows answers 502 with
// the no-target text and reaches neither the header target nor the default.
func TestMissingStoredTargetIsRefusedInEveryFlow_C_e1860d3e(t *testing.T) {
	h := testHandler()
	upstreamB, statsB := countingUpstream(t)
	upstreamC, statsC := countingUpstream(t)
	h.cfg.DefaultTarget = upstreamC.URL

	recorders := callFlows(t, h, "", upstreamB.URL)

	for flow, rw := range recorders {
		if rw.Code != http.StatusBadGateway {
			t.Fatalf("flow %d: status = %d, want %d (body: %s)", flow, rw.Code, http.StatusBadGateway, rw.Body.String())
		}
		if body := strings.TrimSpace(rw.Body.String()); body != "bad gateway: no target URL stored for this credential" {
			t.Fatalf("flow %d: body = %q, want %q", flow, body, "bad gateway: no target URL stored for this credential")
		}
	}
	if got, _, _ := statsB(); got != 0 {
		t.Fatalf("the header target received %d requests, want 0", got)
	}
	if got, _, _ := statsC(); got != 0 {
		t.Fatalf("the default target received %d requests, want 0", got)
	}
}

// assertInvalidTargetRefused runs the generic and digest flows against one
// invalid stored target and asserts the refusal.
func assertInvalidTargetRefused(t *testing.T, target string) {
	t.Helper()

	h := testHandler()
	upstreamB, statsB := countingUpstream(t)
	upstreamC, statsC := countingUpstream(t)
	h.cfg.DefaultTarget = upstreamC.URL

	saved := http.DefaultTransport
	var attempted []string
	http.DefaultTransport = testRoundTripper(func(r *http.Request) (*http.Response, error) {
		attempted = append(attempted, r.URL.String())
		return nil, io.ErrClosedPipe
	})
	defer func() { http.DefaultTransport = saved }()

	recorders := map[string]*httptest.ResponseRecorder{
		"generic": callGenericFlow(t, h, bearerCredential(target, storedTargetTokenA), upstreamB.URL),
		"digest":  callDigestFlow(t, h, target, upstreamB.URL),
	}
	for flow, rw := range recorders {
		if rw.Code != http.StatusBadGateway {
			t.Fatalf("%q, %s: status = %d, want %d (body: %s)", target, flow, rw.Code, http.StatusBadGateway, rw.Body.String())
		}
		if body := strings.TrimSpace(rw.Body.String()); body != "bad gateway: invalid target URL" {
			t.Fatalf("%q, %s: body = %q, want %q", target, flow, body, "bad gateway: invalid target URL")
		}
	}
	if len(attempted) != 0 {
		t.Fatalf("the invalid stored target %q reached the transport: %v", target, attempted)
	}
	if got, _, _ := statsB(); got != 0 {
		t.Fatalf("%q: the header target received %d requests, want 0", target, got)
	}
	if got, _, _ := statsC(); got != 0 {
		t.Fatalf("%q: the default target received %d requests, want 0", target, got)
	}
}

// TestNonHTTPStoredTargetIsRefused covers the scenario "a stored target that is
// not an http or https URL is refused": the generic and digest flows answer 502
// with the invalid-target text and no request leaves the proxy.
func TestNonHTTPStoredTargetIsRefused_C_833affe8(t *testing.T) {
	for _, target := range []string{"ssh://host:22", "/relative/path", "http://", "://x"} {
		assertInvalidTargetRefused(t, target)
	}
}

// TestStoredTargetOfMissingAndPresentCredential covers the scenario "a missing
// credential response has no target": no stored target gives the no-target text,
// and a stored https URL is parsed and used (so the text is empty).
func TestStoredTargetOfMissingAndPresentCredential_C_d6cbb9f7(t *testing.T) {
	h := testHandler()
	upstreamB, statsB := countingUpstream(t)
	h.cfg.DefaultTarget = upstreamB.URL

	missing := callGenericFlow(t, h, bearerCredential("", storedTargetTokenA), upstreamB.URL)
	if missing.Code != http.StatusBadGateway {
		t.Fatalf("no stored target: status = %d, want %d (body: %s)", missing.Code, http.StatusBadGateway, missing.Body.String())
	}
	if body := strings.TrimSpace(missing.Body.String()); body != "bad gateway: no target URL stored for this credential" {
		t.Fatalf("no stored target: body = %q, want %q", body, "bad gateway: no target URL stored for this credential")
	}
	if got, _, _ := statsB(); got != 0 {
		t.Fatalf("no stored target: the header target received %d requests, want 0", got)
	}

	// A stored https URL is parsed and used: the generic flow reaches it, so
	// the no-target text was empty.
	saved := http.DefaultTransport
	var gotURL string
	http.DefaultTransport = testRoundTripper(func(r *http.Request) (*http.Response, error) {
		if r.URL.Host == "api.example.test" {
			gotURL = r.URL.String()
			return &http.Response{
				Status:     "200 OK",
				StatusCode: http.StatusOK,
				Header:     make(http.Header),
				Body:       io.NopCloser(strings.NewReader("{}")),
				Request:    r,
			}, nil
		}
		return saved.RoundTrip(r)
	})
	defer func() { http.DefaultTransport = saved }()

	present := callGenericFlow(t, h, bearerCredential("https://api.example.test/base", storedTargetTokenA), "")
	if present.Code != http.StatusOK {
		t.Fatalf("stored https target: status = %d, want %d (body: %s)", present.Code, http.StatusOK, present.Body.String())
	}
	if gotURL == "" {
		t.Fatal("stored https target: the request did not reach api.example.test")
	}
	if gotURL != "https://api.example.test/base/echo" {
		t.Fatalf("stored https target: upstream URL = %q, want %q", gotURL, "https://api.example.test/base/echo")
	}
}
