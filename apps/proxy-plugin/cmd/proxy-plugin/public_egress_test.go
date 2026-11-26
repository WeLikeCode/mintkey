package main

// Tests for the proxy's connect-time egress guard (proxy-public-egress): a
// credential whose egress scope is anything other than the empty string or
// "any" may connect only to public addresses, whatever the stored target's
// name resolves to when the request is made. The scope travels in the
// x-mintkey-egress-scope response header of the vault GetCredential call and
// in the EgressScope field of vault.GetCredentialResponse; the header-reading
// path (generic, classical key) and the direct-call path (digest, the two
// OAuth2 flows) are both exercised.
//
// Every test first requires the EgressScope field on
// vault.GetCredentialResponse by reflection, so the whole file stays red at
// the base for that one reason, until the proxy reads the scope and guards
// the connection.
//
// Design D9: this file defines its own helpers (startScopedFakeVault,
// scopedFlows) and reuses countingUpstream of stored_target_test.go; it edits
// no other test file.

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"reflect"
	"strings"
	"testing"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/classicalkey"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/proto"
)

// publicEgressChildEnv marks the child process of
// TestPublicScopeIgnoresProxyEnvironment; without it the child test does
// nothing beyond the EgressScope field check.
const publicEgressChildEnv = "PUBLIC_EGRESS_PROXY_CHILD"

// requireScopeField fails the test while vault.GetCredentialResponse carries
// no EgressScope field: the proxy must read x-mintkey-egress-scope from the
// vault response before the public-egress guard can be exercised at all.
func requireScopeField(t *testing.T) {
	t.Helper()
	if _, ok := reflect.TypeOf(vault.GetCredentialResponse{}).FieldByName("EgressScope"); !ok {
		t.Fatalf("vault.GetCredentialResponse has no EgressScope field: the proxy must read the egress scope from the vault response header before the public-egress guard can be tested")
	}
}

// setEgressScope sets the egress scope on a direct-flow credential by
// reflection, so the test file compiles before the field exists.
func setEgressScope(t *testing.T, cred *vault.GetCredentialResponse, scope string) {
	t.Helper()
	requireScopeField(t)
	reflect.ValueOf(cred).Elem().FieldByName("EgressScope").SetString(scope)
}

// scopedFakeVaultServer answers GetCredential with a clone of one response and
// sets one x-mintkey-egress-scope response-header pair per given scope; with
// no scope it sets no header.
type scopedFakeVaultServer struct {
	vaultv1.UnimplementedVaultAdapterServer
	resp   *vaultv1.GetCredentialResponse
	scopes []string
}

func (f *scopedFakeVaultServer) GetCredential(ctx context.Context, _ *vaultv1.GetCredentialRequest) (*vaultv1.GetCredentialResponse, error) {
	if len(f.scopes) > 0 {
		md := metadata.MD{}
		md.Set("x-mintkey-egress-scope", f.scopes...)
		if err := grpc.SetHeader(ctx, md); err != nil {
			return nil, err
		}
	}
	if f.resp == nil {
		return nil, nil
	}
	return proto.Clone(f.resp).(*vaultv1.GetCredentialResponse), nil
}

// startScopedFakeVault serves GetCredential on 127.0.0.1:0 with one
// x-mintkey-egress-scope response-header pair per given scope and returns a
// client for it.
func startScopedFakeVault(t *testing.T, resp *vaultv1.GetCredentialResponse, scopes ...string) *vault.Client {
	t.Helper()

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen for the scoped fake vault: %v", err)
	}
	srv := grpc.NewServer()
	vaultv1.RegisterVaultAdapterServer(srv, &scopedFakeVaultServer{resp: resp, scopes: scopes})
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(srv.Stop)

	client := vault.NewClient(lis.Addr().String(), "", "")
	t.Cleanup(func() { _ = client.Close() })
	return client
}

// publicEgressCallCtx bounds one flow call with five seconds: the guard
// answers immediately, but a resolver that answers nothing may hold the
// request for seconds, and the scenarios name a five-second tolerance.
func publicEgressCallCtx() (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), 5*time.Second)
}

// scopedGenericFlow runs the generic injector of ServeHTTP with the egress
// scope carried in the fake vault's response header.
func scopedGenericFlow(t *testing.T, h *proxyHandler, resp *vaultv1.GetCredentialResponse, scopes ...string) *httptest.ResponseRecorder {
	t.Helper()

	h.vaultClient = startScopedFakeVault(t, resp, scopes...)
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, nil)
	h.pubKeys["testkey"] = pub

	ctx, cancel := publicEgressCallCtx()
	defer cancel()
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil).WithContext(ctx)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	return rw
}

// scopedClassicalFlow runs the classical service key path of ServeHTTP with
// the egress scope carried in the fake vault's response header.
func scopedClassicalFlow(t *testing.T, h *proxyHandler, resp *vaultv1.GetCredentialResponse, scopes ...string) *httptest.ResponseRecorder {
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
	h.vaultClient = startScopedFakeVault(t, resp, scopes...)

	ctx, cancel := publicEgressCallCtx()
	defer cancel()
	req := httptest.NewRequest(http.MethodGet, "/"+testSvcUUIDA+"/echo", nil).WithContext(ctx)
	req.Header.Set("Authorization", "Bearer "+storedTargetClassicalKey)
	req.Header.Set("X-Mintkey-Service-ID", testSvcUUIDA)
	req.Header.Set("X-Mintkey-Tenant-ID", "tenant-test-uuid-0001")
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	return rw
}

// scopedDigestFlow runs handleHTTPDigest directly, with the scope set on the
// credential by reflection.
func scopedDigestFlow(t *testing.T, h *proxyHandler, target, scope string) *httptest.ResponseRecorder {
	t.Helper()

	cred := &vault.GetCredentialResponse{
		AuthScheme: int32(credential.AuthSchemeHTTPDigest),
		Plaintext:  []byte(`{"public_key":"pk-test","private_key":"sk-test"}`),
		TargetURL:  target,
	}
	setEgressScope(t, cred, scope)
	ctx, cancel := publicEgressCallCtx()
	defer cancel()
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil).WithContext(ctx)
	rw := httptest.NewRecorder()
	h.handleHTTPDigest(rw, req, cred, "tenant-test-uuid-0001", testSvcUUIDA, "agent_digest", time.Now())
	return rw
}

// scopedClientCredentialsFlow runs handleOAuth2ClientCredentials directly, with
// the scope set on the credential by reflection.
func scopedClientCredentialsFlow(t *testing.T, h *proxyHandler, target, scope, tokenURL string) *httptest.ResponseRecorder {
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
	setEgressScope(t, cred, scope)
	ctx, cancel := publicEgressCallCtx()
	defer cancel()
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil).WithContext(ctx)
	rw := httptest.NewRecorder()
	h.handleOAuth2ClientCredentials(rw, req, cred, "tenant-test-uuid-0001", testSvcUUIDA, "agent_cc", time.Now())
	return rw
}

// scopedPasswordGrantFlow runs handleOAuth2PasswordGrant directly, with the
// scope set on the credential by reflection.
func scopedPasswordGrantFlow(t *testing.T, h *proxyHandler, target, scope, tokenURL string) *httptest.ResponseRecorder {
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
	setEgressScope(t, cred, scope)
	ctx, cancel := publicEgressCallCtx()
	defer cancel()
	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil).WithContext(ctx)
	rw := httptest.NewRecorder()
	h.handleOAuth2PasswordGrant(rw, req, cred, "tenant-test-uuid-0001", testSvcUUIDA, "agent_pg", time.Now())
	return rw
}

// scopedFlows runs the five flows against one stored target with one egress
// scope and returns their recorders: generic, classical key, digest, client
// credentials and password grant. The generic and classical-key flows get the
// scope from the fake vault's response header, the three direct calls from the
// credential field, so both paths the proxy reads the scope from are exercised.
func scopedFlows(t *testing.T, h *proxyHandler, target, scope string) []*httptest.ResponseRecorder {
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
		scopedGenericFlow(t, h, &vaultv1.GetCredentialResponse{
			AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
			Value:      []byte(storedTargetTokenA),
			TargetUrl:  target,
		}, scope),
		scopedClassicalFlow(t, h, &vaultv1.GetCredentialResponse{
			AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
			Value:      []byte("classical-" + "secret-" + "value"),
			HeaderName: "X-Api-Key",
			TargetUrl:  target,
		}, scope),
		scopedDigestFlow(t, h, target, scope),
		scopedClientCredentialsFlow(t, h, target, scope, tokenSrv.URL),
		scopedPasswordGrantFlow(t, h, target, scope, tokenSrv.URL),
	}
}

// scopedFlowName returns the flow's name for failure messages, in the order
// scopedFlows returns the recorders.
func scopedFlowName(i int) string {
	names := []string{"generic", "classical-key", "digest", "oauth2-client-credentials", "oauth2-password-grant"}
	if i < 0 || i >= len(names) {
		return "flow"
	}
	return names[i]
}

// assertFlowNotAllowed asserts one flow's refusal: 502 with the not-allowed
// text.
func assertFlowNotAllowed(t *testing.T, flow string, rw *httptest.ResponseRecorder) {
	t.Helper()
	if rw.Code != http.StatusBadGateway {
		t.Fatalf("%s flow: status = %d, want %d (body: %s)", flow, rw.Code, http.StatusBadGateway, rw.Body.String())
	}
	if body := strings.TrimSpace(rw.Body.String()); body != "bad gateway: target address not allowed" {
		t.Fatalf("%s flow: body = %q, want %q", flow, body, "bad gateway: target address not allowed")
	}
}

// assertFlowReached asserts one flow's request reached the local server: the
// server's bare 200 came back.
func assertFlowReached(t *testing.T, flow string, rw *httptest.ResponseRecorder) {
	t.Helper()
	if rw.Code != http.StatusOK {
		t.Fatalf("%s flow: status = %d, want %d (body: %s)", flow, rw.Code, http.StatusOK, rw.Body.String())
	}
}

// assertAllFlowsNotAllowed asserts the refusal of every flow in the order
// scopedFlows returns them.
func assertAllFlowsNotAllowed(t *testing.T, recorders []*httptest.ResponseRecorder) {
	t.Helper()
	for i, rw := range recorders {
		assertFlowNotAllowed(t, scopedFlowName(i), rw)
	}
}

// assertAllFlowsReached asserts every flow in the order scopedFlows returns
// them reached the local server.
func assertAllFlowsReached(t *testing.T, recorders []*httptest.ResponseRecorder) {
	t.Helper()
	for i, rw := range recorders {
		assertFlowReached(t, scopedFlowName(i), rw)
	}
}

// bearerScopeResp and apiKeyScopeResp build the credentials of the generic and
// the classical-key flow against one target.
func bearerScopeResp(target string) *vaultv1.GetCredentialResponse {
	return &vaultv1.GetCredentialResponse{
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
		Value:      []byte(storedTargetTokenA),
		TargetUrl:  target,
	}
}

func apiKeyScopeResp(target string) *vaultv1.GetCredentialResponse {
	return &vaultv1.GetCredentialResponse{
		AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
		Value:      []byte("classical-" + "secret-" + "value"),
		HeaderName: "X-Api-Key",
		TargetUrl:  target,
	}
}

// TestPublicScopeRefusesNonPublicTargets_C_bd7857b1 covers the scenario "a
// public credential is never sent to a non-public address": for every target
// of the scenario, used by each of the five flows, the answer is 502 with the
// not-allowed text and the local httptest server received no request.
func TestPublicScopeRefusesNonPublicTargets_C_bd7857b1(t *testing.T) {
	requireScopeField(t)

	upstream, stats := countingUpstream(t)
	targets := []string{
		upstream.URL,
		"http://127.0.0.1:9",
		"http://[::1]:9",
		"http://10.1.2.3",
		"http://10.255.255.255",
		"http://172.16.0.9",
		"http://172.31.255.255",
		"http://192.168.1.5",
		"http://169.254.169.254",
		"http://100.64.0.0",
		"http://100.64.0.1",
		"http://100.127.255.255",
		"http://[fd00::1]",
		"http://[fe80::1]",
		"http://224.0.0.1",
		"http://239.255.255.255",
		"http://[ff02::1]",
		"http://0.0.0.0",
		"http://[::]",
		"http://255.255.255.255",
		"http://240.0.0.1",
		"http://[::ffff:10.0.0.1]",
		"http://[::ffff:7f00:1]",
	}
	for _, target := range targets {
		recorders := scopedFlows(t, testHandler(), target, "public")
		assertAllFlowsNotAllowed(t, recorders)
	}
	if got, _, _ := stats(); got != 0 {
		t.Fatalf("the local server received %d requests, want 0", got)
	}
}

// TestPublicScopeRefusesLoopbackName_C_37681a78 covers the scenario "a name
// that resolves only to loopback is refused": the stored target
// http://localhost:<port of a local server>, used by each of the five flows,
// is refused with the not-allowed text, and the local server received no
// request (the guard resolves the name itself).
func TestPublicScopeRefusesLoopbackName_C_37681a78(t *testing.T) {
	requireScopeField(t)

	upstream, stats := countingUpstream(t)
	_, port, err := net.SplitHostPort(strings.TrimPrefix(upstream.URL, "http://"))
	if err != nil {
		t.Fatalf("split the port of the local server: %v", err)
	}
	recorders := scopedFlows(t, testHandler(), "http://localhost:"+port, "public")
	assertAllFlowsNotAllowed(t, recorders)
	if got, _, _ := stats(); got != 0 {
		t.Fatalf("the local server received %d requests, want 0", got)
	}
}

// TestPublicScopeNameWithoutAddress_C_bd037c93 covers the scenario "a name
// that answers no address is refused": the stored target
// http://no-such-host.invalid, with a request context that ends after five
// seconds and nothing listening for it, is refused with the upstream
// unreachable text by every flow, and never with the not-allowed text (a
// lookup that fails or answers nothing is an error that does not name a
// non-public address).
func TestPublicScopeNameWithoutAddress_C_bd037c93(t *testing.T) {
	requireScopeField(t)

	recorders := scopedFlows(t, testHandler(), "http://no-such-host.invalid", "public")
	for i, rw := range recorders {
		if rw.Code != http.StatusBadGateway {
			t.Fatalf("%s flow: status = %d, want %d (body: %s)", scopedFlowName(i), rw.Code, http.StatusBadGateway, rw.Body.String())
		}
		if body := strings.TrimSpace(rw.Body.String()); body != "bad gateway: upstream unreachable" {
			t.Fatalf("%s flow: body = %q, want %q (a lookup that answers nothing must not name a non-public address)", scopedFlowName(i), body, "bad gateway: upstream unreachable")
		}
	}
}

// TestOtherScopesAreUnchanged_C_e16db2b8 covers the scenario "the other scopes
// are unchanged": the same local server is the stored target with scope any
// and with no scope, and each of the five flows reaches it and returns its
// answer.
func TestOtherScopesAreUnchanged_C_e16db2b8(t *testing.T) {
	requireScopeField(t)

	for _, scope := range []string{"any", ""} {
		upstream, stats := countingUpstream(t)
		recorders := scopedFlows(t, testHandler(), upstream.URL, scope)
		assertAllFlowsReached(t, recorders)
		if got, _, _ := stats(); got != 5 {
			t.Fatalf("scope %q: the local server received %d requests, want 5 (one per flow)", scope, got)
		}
	}
}

// TestUnknownScopeIsTreatedAsPublic_C_ed224807 covers the scenario "an unknown
// scope is treated as public": with the credential's scope bogus and the local
// server as the stored target, the answer is 502 with the not-allowed text.
func TestUnknownScopeIsTreatedAsPublic_C_ed224807(t *testing.T) {
	requireScopeField(t)

	upstream, stats := countingUpstream(t)
	recorders := scopedFlows(t, testHandler(), upstream.URL, "bogus")
	assertAllFlowsNotAllowed(t, recorders)
	if got, _, _ := stats(); got != 0 {
		t.Fatalf("the local server received %d requests, want 0", got)
	}
}

// TestScopeArrivesFromVault_C_b5f6f1f1 covers the scenario "the scope arrives
// from the vault": a fake vault gRPC server answers GetCredential with the
// response header x-mintkey-egress-scope, for the generic flow and the
// classical-key flow. With the value public both answers are the 502; with the
// value any and with no header both reach the server; with two values of the
// header (any twice) both answers are the 502 again.
func TestScopeArrivesFromVault_C_b5f6f1f1(t *testing.T) {
	requireScopeField(t)

	// The header holds public: both flows refuse the loopback target.
	upstream, stats := countingUpstream(t)
	generic := scopedGenericFlow(t, testHandler(), bearerScopeResp(upstream.URL), "public")
	assertFlowNotAllowed(t, "generic", generic)
	classical := scopedClassicalFlow(t, testHandler(), apiKeyScopeResp(upstream.URL), "public")
	assertFlowNotAllowed(t, "classical", classical)
	if got, _, _ := stats(); got != 0 {
		t.Fatalf("header public: the local server received %d requests, want 0", got)
	}

	// The header holds any, and no header at all: both flows reach the server.
	for _, tc := range []struct {
		name   string
		scopes []string
	}{
		{"any", []string{"any"}},
		{"no header", nil},
	} {
		upstreamAny, statsAny := countingUpstream(t)
		g := scopedGenericFlow(t, testHandler(), bearerScopeResp(upstreamAny.URL), tc.scopes...)
		assertFlowReached(t, "generic", g)
		c := scopedClassicalFlow(t, testHandler(), apiKeyScopeResp(upstreamAny.URL), tc.scopes...)
		assertFlowReached(t, "classical", c)
		if got, _, _ := statsAny(); got != 2 {
			t.Fatalf("header %s: the local server received %d requests, want 2", tc.name, got)
		}
	}

	// Two values of the header (any twice): both flows refuse again.
	upstreamTwice, statsTwice := countingUpstream(t)
	g2 := scopedGenericFlow(t, testHandler(), bearerScopeResp(upstreamTwice.URL), "any", "any")
	assertFlowNotAllowed(t, "generic", g2)
	c2 := scopedClassicalFlow(t, testHandler(), apiKeyScopeResp(upstreamTwice.URL), "any", "any")
	assertFlowNotAllowed(t, "classical", c2)
	if got, _, _ := statsTwice(); got != 0 {
		t.Fatalf("two header values: the local server received %d requests, want 0", got)
	}
}

// childProxyEnvironment is the parent's environment with every proxy variable
// removed, so the child runs with HTTP_PROXY and HTTPS_PROXY set to a
// documentation address and no NO_PROXY.
func childProxyEnvironment() []string {
	var env []string
	for _, kv := range os.Environ() {
		switch {
		case strings.HasPrefix(kv, "HTTP_PROXY="), strings.HasPrefix(kv, "http_proxy="),
			strings.HasPrefix(kv, "HTTPS_PROXY="), strings.HasPrefix(kv, "https_proxy="),
			strings.HasPrefix(kv, "NO_PROXY="), strings.HasPrefix(kv, "no_proxy="):
		default:
			env = append(env, kv)
		}
	}
	return append(env, "HTTP_PROXY=http://192.0.2.1:3128", "HTTPS_PROXY=http://192.0.2.1:3128")
}

// TestPublicScopeIgnoresProxyEnvironment_C_0770d694 covers the scenario "an
// environment proxy is never used": it runs a child process of the test
// binary with HTTP_PROXY and HTTPS_PROXY set to http://192.0.2.1:3128 (a
// documentation address, public to the guard) and no NO_PROXY, and fails
// unless the child exits 0. A transport that honoured the variables would dial
// the proxy address, pass the guard and answer upstream unreachable.
func TestPublicScopeIgnoresProxyEnvironment_C_0770d694(t *testing.T) {
	requireScopeField(t)

	cmd := exec.Command(os.Args[0], "-test.run=^TestPublicScopeIgnoresProxyEnvironmentChild$", "-test.timeout=90s")
	cmd.Env = append(childProxyEnvironment(), publicEgressChildEnv+"=1")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("the child test did not exit 0: %v\n%s", err, out)
	}
}

// TestPublicScopeIgnoresProxyEnvironmentChild is the child of
// TestPublicScopeIgnoresProxyEnvironment. Run in the normal suite it does
// nothing beyond the EgressScope field check; with the marker set it makes the
// five calls with scope public, the stored target http://10.1.2.3 and a
// request context that ends after five seconds, and passes only when every
// flow answered 502 with the not-allowed text.
func TestPublicScopeIgnoresProxyEnvironmentChild(t *testing.T) {
	requireScopeField(t)
	if os.Getenv(publicEgressChildEnv) != "1" {
		return
	}

	recorders := scopedFlows(t, testHandler(), "http://10.1.2.3", "public")
	assertAllFlowsNotAllowed(t, recorders)
}
