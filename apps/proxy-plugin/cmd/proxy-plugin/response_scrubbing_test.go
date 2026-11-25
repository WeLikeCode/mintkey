package main

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"encoding/base64"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
)

// Test values of the scenarios, built from parts so no secret-shaped literal is
// written in this file. <tokenA> and <tokenB> come from stored_target_test.go.
var (
	scrubTokenC = "pass" + " " + "word" + "&x=" + "1234"
	scrubSKey   = "sk_" + "live_" + "abcdefghijkl"
	scrubAPIKey = "api_" + "key=" + "abcdefghij012345"
)

// scrubJWTValue builds the <jwt> of the spec: base64url of the header JSON, of
// the payload JSON and of 32 bytes of 0x01, joined by dots without padding.
func scrubJWTValue() string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	payload := base64.RawURLEncoding.EncodeToString([]byte(`{"sub":"x"}`))
	signature := base64.RawURLEncoding.EncodeToString(bytes.Repeat([]byte{1}, 32))
	return header + "." + payload + "." + signature
}

// enableScrubPatterns loads the config with the setting on and installs it on
// the handler. It reads the field through reflection so the test compiles
// before the field exists.
func enableScrubPatterns(t *testing.T, h *proxyHandler) {
	t.Helper()

	t.Setenv("MINTKEY_PROXY_SCRUB_PATTERNS", "true")
	cfg := config.Load()
	field := reflect.ValueOf(cfg).Elem().FieldByName("ScrubPatterns")
	if !field.IsValid() {
		t.Fatal("config.Config has no ScrubPatterns field; cannot read MINTKEY_PROXY_SCRUB_PATTERNS")
	}
	if field.Kind() != reflect.Bool {
		t.Fatalf("config.Config.ScrubPatterns has kind %s, want bool", field.Kind())
	}
	if !field.Bool() {
		t.Fatal("ScrubPatterns = false with MINTKEY_PROXY_SCRUB_PATTERNS=true")
	}
	h.cfg = cfg
}

// assertNoSecret fails when the recorder's body or any header value holds one
// of the secrets.
func assertNoSecret(t *testing.T, rw *httptest.ResponseRecorder, secrets ...string) {
	t.Helper()

	body := rw.Body.String()
	for _, secret := range secrets {
		if secret == "" {
			continue
		}
		if strings.Contains(body, secret) {
			t.Fatalf("response body holds the secret %q: %s", secret, body)
		}
		for name, values := range rw.Header() {
			for _, value := range values {
				if strings.Contains(value, secret) {
					t.Fatalf("response header %s holds the secret %q: %q", name, secret, value)
				}
			}
		}
	}
}

// genericFlowWithHeaders runs the generic injector of ServeHTTP with caller
// headers of the test's choosing.
func genericFlowWithHeaders(t *testing.T, h *proxyHandler, cred *vaultv1.GetCredentialResponse, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()

	h.vaultClient = startFakeVault(t, cred)
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, nil)
	h.pubKeys["testkey"] = pub

	req := httptest.NewRequest(http.MethodGet, "/v1/call/"+testSvcUUIDA+"/echo", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	for name, value := range headers {
		req.Header.Set(name, value)
	}
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	return rw
}

// TestUpstreamEchoDoesNotReachTheCaller_C_d3007570 covers the scenario "a
// credential echoed by the upstream does not reach the caller": both the
// generic and the classical-key flow echo the injected value, and the exact
// value is redacted with the pattern rules off and on; Set-Cookie follows the
// setting.
func TestUpstreamEchoDoesNotReachTheCaller_C_d3007570(t *testing.T) {
	const expectedBody = `{"echo":"Bearer [REDACTED]","other":"fine"}`

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		value := r.Header.Get("X-Api-Key")
		if value == "" {
			value = strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Echo", value)
		w.Header().Set("Set-Cookie", "sid=abc12345")
		w.WriteHeader(http.StatusOK)
		_, _ = fmt.Fprintf(w, `{"echo":"Bearer %s","other":"fine"}`, value)
	}))
	t.Cleanup(upstream.Close)

	run := func(t *testing.T, patterns bool) map[string]*httptest.ResponseRecorder {
		t.Helper()

		h := testHandler()
		if patterns {
			enableScrubPatterns(t, h)
		}
		return map[string]*httptest.ResponseRecorder{
			"generic": callGenericFlow(t, h, bearerCredential(upstream.URL, storedTargetTokenA), ""),
			"classical": callClassicalFlow(t, h, &vaultv1.GetCredentialResponse{
				AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_API_KEY_HEADER,
				Value:      []byte(storedTargetTokenA),
				HeaderName: "X-Api-Key",
				TargetUrl:  upstream.URL,
			}, ""),
		}
	}

	for _, patterns := range []bool{false, true} {
		recorders := run(t, patterns)
		for flow, rw := range recorders {
			if rw.Code != http.StatusOK {
				t.Fatalf("%s (patterns=%v): status = %d, want %d (body: %s)", flow, patterns, rw.Code, http.StatusOK, rw.Body.String())
			}
			if got := rw.Body.String(); got != expectedBody {
				t.Fatalf("%s (patterns=%v): body = %q, want %q", flow, patterns, got, expectedBody)
			}
			if got := rw.Header().Get("X-Echo"); got != "[REDACTED]" {
				t.Fatalf("%s (patterns=%v): X-Echo = %q, want %q", flow, patterns, got, "[REDACTED]")
			}
			assertNoSecret(t, rw, storedTargetTokenA)

			setCookie, present := rw.Header()["Set-Cookie"]
			if patterns {
				if present {
					t.Fatalf("%s (patterns=true): Set-Cookie = %v, want the header removed", flow, setCookie)
				}
				continue
			}
			if !present || len(setCookie) != 1 || setCookie[0] != "sid=abc12345" {
				t.Fatalf("%s (patterns=false): Set-Cookie = %v, want [sid=abc12345]", flow, setCookie)
			}
		}
	}
}

// TestPatternRulesFollowTheSetting_C_dbc89858 covers the scenario "the pattern
// rules apply only when the setting is on": a clean-shaped body passes through
// byte for byte with the setting off, and its JWT, sk_/pk_ and api_key values
// are replaced with the scrubber's markers with the setting on.
func TestPatternRulesFollowTheSetting_C_dbc89858(t *testing.T) {
	jwtValue := scrubJWTValue()
	body := fmt.Sprintf(`{"jwt":%q,"key":%q,"q":%q}`, jwtValue, scrubSKey, scrubAPIKey)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Set-Cookie", "sid=abc12345")
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, body)
	}))
	t.Cleanup(upstream.Close)

	// The setting off (testHandler's config) passes the response through.
	off := testHandler()
	offRec := callGenericFlow(t, off, bearerCredential(upstream.URL, storedTargetTokenA), "")
	if offRec.Code != http.StatusOK {
		t.Fatalf("patterns=false: status = %d, want %d (body: %s)", offRec.Code, http.StatusOK, offRec.Body.String())
	}
	if got := offRec.Body.String(); got != body {
		t.Fatalf("patterns=false: body = %q, want it byte for byte %q", got, body)
	}
	if got := offRec.Header().Get("Set-Cookie"); got != "sid=abc12345" {
		t.Fatalf("patterns=false: Set-Cookie = %q, want %q", got, "sid=abc12345")
	}

	// The setting on applies the pattern rules.
	on := testHandler()
	enableScrubPatterns(t, on)
	onRec := callGenericFlow(t, on, bearerCredential(upstream.URL, storedTargetTokenA), "")
	if onRec.Code != http.StatusOK {
		t.Fatalf("patterns=true: status = %d, want %d (body: %s)", onRec.Code, http.StatusOK, onRec.Body.String())
	}
	wantBody := fmt.Sprintf(`{"jwt":%q,"key":%q,"q":%q}`, "[REDACTED_JWT]", "[REDACTED]", "api_key=[REDACTED]")
	if got := onRec.Body.String(); got != wantBody {
		t.Fatalf("patterns=true: body = %q, want %q", got, wantBody)
	}
	if _, present := onRec.Header()["Set-Cookie"]; present {
		t.Fatalf("patterns=true: Set-Cookie = %v, want the header removed", onRec.Header()["Set-Cookie"])
	}
}

// TestExchangedTokenIsRedacted_C_ff10cd06 covers the scenario "the exchanged
// token of the OAuth2 flows is redacted too": the client-credentials and
// password-grant flows echo the token they injected, and the caller sees the
// redaction marker instead.
func TestExchangedTokenIsRedacted_C_ff10cd06(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = fmt.Fprintf(w, `{"echo":%q}`, token)
	}))
	t.Cleanup(upstream.Close)

	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprintf(w, `{"access_token":%q,"token":%q,"expires_in":3600}`, storedTargetTokenB, storedTargetTokenB)
	}))
	t.Cleanup(tokenSrv.Close)

	h := testHandler()
	recorders := map[string]*httptest.ResponseRecorder{
		"client-credentials": callClientCredentialsFlow(t, h, upstream.URL, "", tokenSrv.URL),
		"password-grant":     callPasswordGrantFlow(t, h, upstream.URL, "", tokenSrv.URL),
	}

	for flow, rw := range recorders {
		if rw.Code != http.StatusOK {
			t.Fatalf("%s: status = %d, want %d (body: %s)", flow, rw.Code, http.StatusOK, rw.Body.String())
		}
		if body := rw.Body.String(); !strings.Contains(body, "[REDACTED]") {
			t.Fatalf("%s: body = %q, want it to hold [REDACTED]", flow, body)
		}
		assertNoSecret(t, rw, storedTargetTokenB)
	}
}

// TestCleanResponsePassesThrough_C_c2fde988 covers the scenario "a clean
// response passes through unchanged": each of the five flows forwards the
// upstream's 404, its header, its body bytes and its Content-Length. The last
// part sends the caller's Accept-Encoding through the generic flow: the
// upstream proxy replaces it with the transport's own gzip before the request
// leaves, so the clean body is scanned and forwarded rather than streamed as an
// encoding the proxy cannot read.
func TestCleanResponsePassesThrough_C_c2fde988(t *testing.T) {
	cleanBody := `{"ok":true,"message":"all good"}`

	var mu sync.Mutex
	var encodings []string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		encodings = append(encodings, r.Header.Get("Accept-Encoding"))
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Request-Id", "r-1")
		w.Header().Set("Content-Length", strconv.Itoa(len(cleanBody)))
		w.WriteHeader(http.StatusNotFound)
		_, _ = io.WriteString(w, cleanBody)
	}))
	t.Cleanup(upstream.Close)

	recorders := callFlows(t, testHandler(), upstream.URL, "")
	flows := []string{"generic", "classical-key", "digest", "client-credentials", "password-grant"}
	for flow, rw := range recorders {
		if rw.Code != http.StatusNotFound {
			t.Fatalf("%s: status = %d, want %d (body: %s)", flows[flow], rw.Code, http.StatusNotFound, rw.Body.String())
		}
		if got := rw.Header().Get("X-Request-Id"); got != "r-1" {
			t.Fatalf("%s: X-Request-Id = %q, want %q", flows[flow], got, "r-1")
		}
		if got := rw.Body.String(); got != cleanBody {
			t.Fatalf("%s: body = %q, want %q", flows[flow], got, cleanBody)
		}
		if got, want := rw.Header().Get("Content-Length"), strconv.Itoa(len(cleanBody)); got != want {
			t.Fatalf("%s: Content-Length = %q, want %q", flows[flow], got, want)
		}
	}

	mu.Lock()
	before := len(encodings)
	mu.Unlock()

	extra := genericFlowWithHeaders(t, testHandler(),
		bearerCredential(upstream.URL, storedTargetTokenA),
		map[string]string{"Accept-Encoding": "br"})
	if extra.Code != http.StatusNotFound {
		t.Fatalf("Accept-Encoding=br: status = %d, want %d (body: %s)", extra.Code, http.StatusNotFound, extra.Body.String())
	}
	if got := extra.Body.String(); got != cleanBody {
		t.Fatalf("Accept-Encoding=br: body = %q, want %q", got, cleanBody)
	}
	if got := extra.Header().Get("X-Request-Id"); got != "r-1" {
		t.Fatalf("Accept-Encoding=br: X-Request-Id = %q, want %q", got, "r-1")
	}

	mu.Lock()
	gotEncodings := append([]string(nil), encodings...)
	mu.Unlock()
	if len(gotEncodings) != before+1 {
		t.Fatalf("the Accept-Encoding=br request reached the upstream %d time(s), want once", len(gotEncodings)-before)
	}
	if got := gotEncodings[len(gotEncodings)-1]; got != "gzip" {
		t.Fatalf("upstream Accept-Encoding = %q, want %q (the caller's br must not reach it)", got, "gzip")
	}
}

// TestEventStreamIsNotBuffered_C_e1d174b7 covers the scenario "an event stream
// is not buffered": the first event reaches the caller before the upstream
// finishes, its header value is redacted and its text is passed as written.
func TestEventStreamIsNotBuffered_C_e1d174b7(t *testing.T) {
	release := make(chan struct{})
	released := false

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("X-Echo", storedTargetTokenA)
		w.WriteHeader(http.StatusOK)
		_, _ = fmt.Fprintf(w, "data: %s\n\n", storedTargetTokenA)
		w.(http.Flusher).Flush()
		<-release
	}))

	h := testHandler()
	h.vaultClient = startFakeVault(t, bearerCredential(upstream.URL, storedTargetTokenA))
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, nil)
	h.pubKeys["testkey"] = pub

	srv := httptest.NewServer(h)
	defer func() {
		if !released {
			close(release)
		}
		srv.Close()
		upstream.Close()
	}()

	req, err := http.NewRequest(http.MethodGet, srv.URL+"/v1/call/"+testSvcUUIDA+"/stream", nil)
	if err != nil {
		t.Fatalf("build the request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := srv.Client().Do(req)
	if err != nil {
		t.Fatalf("call the proxy: %v", err)
	}
	defer resp.Body.Close()

	if got := resp.Header.Get("X-Echo"); got != "[REDACTED]" {
		t.Fatalf("X-Echo = %q, want %q", got, "[REDACTED]")
	}

	type readResult struct {
		line string
		err  error
	}
	read := make(chan readResult, 1)
	go func() {
		line, err := bufio.NewReader(resp.Body).ReadString('\n')
		read <- readResult{line: line, err: err}
	}()

	select {
	case result := <-read:
		if result.err != nil {
			t.Fatalf("read the first event: %v", result.err)
		}
		if want := "data: " + storedTargetTokenA + "\n"; result.line != want {
			t.Fatalf("first event = %q, want %q", result.line, want)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("the first event did not arrive within 5 seconds; the stream was buffered")
	}

	// The upstream is still blocked on release, so the event above arrived
	// before it finished.
	close(release)
	released = true
	_, _ = io.Copy(io.Discard, resp.Body)
}

// TestEncodedBodiesAreDecodedOrRefused_C_7d21b6f6 covers the scenario "encoded
// bodies are decoded or refused": the caller's Accept-Encoding is replaced by
// the transport's gzip and decoded, while an encoding the proxy cannot read is
// refused with the encoded-response text.
func TestEncodedBodiesAreDecodedOrRefused_C_7d21b6f6(t *testing.T) {
	seenEncoding := make(chan string, 1)
	gzipUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenEncoding <- r.Header.Get("Accept-Encoding")
		w.Header().Set("Content-Type", "text/plain")
		if strings.Contains(r.Header.Get("Accept-Encoding"), "gzip") {
			w.Header().Set("Content-Encoding", "gzip")
			gz := gzip.NewWriter(w)
			_, _ = io.WriteString(gz, "echo: "+storedTargetTokenA)
			_ = gz.Close()
			return
		}
		_, _ = io.WriteString(w, "echo: "+storedTargetTokenA)
	}))
	t.Cleanup(gzipUpstream.Close)

	decoded := genericFlowWithHeaders(t, testHandler(),
		bearerCredential(gzipUpstream.URL, storedTargetTokenA),
		map[string]string{"Accept-Encoding": "br"})
	if got := <-seenEncoding; got != "gzip" {
		t.Fatalf("upstream Accept-Encoding = %q, want %q only", got, "gzip")
	}
	if decoded.Code != http.StatusOK {
		t.Fatalf("gzip upstream: status = %d, want %d (body: %s)", decoded.Code, http.StatusOK, decoded.Body.String())
	}
	if got := decoded.Body.String(); got != "echo: [REDACTED]" {
		t.Fatalf("gzip upstream: body = %q, want %q", got, "echo: [REDACTED]")
	}

	brUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Encoding", "br")
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, "compressed with br")
	}))
	t.Cleanup(brUpstream.Close)

	refused := callGenericFlow(t, testHandler(), bearerCredential(brUpstream.URL, storedTargetTokenA), "")
	if refused.Code != http.StatusBadGateway {
		t.Fatalf("br upstream: status = %d, want %d (body: %s)", refused.Code, http.StatusBadGateway, refused.Body.String())
	}
	if body := strings.TrimSpace(refused.Body.String()); body != "bad gateway: encoded response not supported" {
		t.Fatalf("br upstream: body = %q, want %q", body, "bad gateway: encoded response not supported")
	}
}

// TestUnreachableUpstreamAnswersWithText_C_ccbb65b9 covers the scenario "an
// unreachable upstream answers 502 with a text": a stored target on a closed
// local port answers with the upstream-unreachable text in every flow.
func TestUnreachableUpstreamAnswersWithText_C_ccbb65b9(t *testing.T) {
	closed := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	closedURL := closed.URL
	closed.Close()

	recorders := callFlows(t, testHandler(), closedURL, "")
	for flow, rw := range recorders {
		if rw.Code != http.StatusBadGateway {
			t.Fatalf("flow %d: status = %d, want %d (body: %s)", flow, rw.Code, http.StatusBadGateway, rw.Body.String())
		}
		if body := strings.TrimSpace(rw.Body.String()); body != "bad gateway: upstream unreachable" {
			t.Fatalf("flow %d: body = %q, want %q", flow, body, "bad gateway: upstream unreachable")
		}
	}
}

// TestSecretInsideLongerValueAndMultiValueHeader_C_b09ecf07 covers the scenario
// "a secret inside a longer value and in a multi-value header": only the
// matching text of each header value is replaced, and each value of a
// multi-value header is scrubbed on its own.
func TestSecretInsideLongerValueAndMultiValueHeader_C_b09ecf07(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Echo", "Bearer "+storedTargetTokenA)
		w.Header().Add("X-Multi", "first="+storedTargetTokenA)
		w.Header().Add("X-Multi", "second=clean")
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(upstream.Close)

	rw := callGenericFlow(t, testHandler(), bearerCredential(upstream.URL, storedTargetTokenA), "")
	if rw.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d (body: %s)", rw.Code, http.StatusOK, rw.Body.String())
	}
	if got := rw.Header().Get("X-Echo"); got != "Bearer [REDACTED]" {
		t.Fatalf("X-Echo = %q, want %q", got, "Bearer [REDACTED]")
	}
	wantMulti := []string{"first=[REDACTED]", "second=clean"}
	gotMulti := rw.Header().Values("X-Multi")
	if len(gotMulti) != len(wantMulti) {
		t.Fatalf("X-Multi = %v, want %v", gotMulti, wantMulti)
	}
	for i := range wantMulti {
		if gotMulti[i] != wantMulti[i] {
			t.Fatalf("X-Multi[%d] = %q, want %q (all: %v)", i, gotMulti[i], wantMulti[i], gotMulti)
		}
	}
}

// TestUndecodableBodyIsRefused_C_b99db4cf covers the scenario "a body that
// fails to decode is refused": an offered gzip with bytes that are not gzip is
// answered with the body-unreadable text, not the unreachable one.
func TestUndecodableBodyIsRefused_C_b99db4cf(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.Header.Get("Accept-Encoding"), "gzip") {
			w.Header().Set("Content-Encoding", "gzip")
		}
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, "not gzip at all")
	}))
	t.Cleanup(upstream.Close)

	rw := callGenericFlow(t, testHandler(), bearerCredential(upstream.URL, storedTargetTokenA), "")
	if rw.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want %d (body: %s)", rw.Code, http.StatusBadGateway, rw.Body.String())
	}
	if body := strings.TrimSpace(rw.Body.String()); body != "bad gateway: upstream response unreadable" {
		t.Fatalf("body = %q, want %q", body, "bad gateway: upstream response unreadable")
	}
}

// TestShortEncodedAndEmptySecrets_C_821c31ba covers the scenario "short
// secrets, encoded forms and empty secrets": a secret shorter than 8 bytes is
// not matched, the raw/base64/query-escaped forms of a longer one are, and an
// empty secret replaces nothing.
func TestShortEncodedAndEmptySecrets_C_821c31ba(t *testing.T) {
	shortSecret := "abc" + "1234"
	shortBody := `{"echo":"` + shortSecret + `"}`
	shortUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, shortBody)
	}))
	t.Cleanup(shortUpstream.Close)

	shortRec := callGenericFlow(t, testHandler(), bearerCredential(shortUpstream.URL, shortSecret), "")
	if got := shortRec.Body.String(); got != shortBody {
		t.Fatalf("short secret: body = %q, want it byte for byte %q", got, shortBody)
	}

	encodedBody := fmt.Sprintf(`{"b64":%q,"q":%q}`,
		base64.StdEncoding.EncodeToString([]byte(scrubTokenC)), url.QueryEscape(scrubTokenC))
	encodedUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, encodedBody)
	}))
	t.Cleanup(encodedUpstream.Close)

	encodedRec := callGenericFlow(t, testHandler(), bearerCredential(encodedUpstream.URL, scrubTokenC), "")
	encodedGot := encodedRec.Body.String()
	if encodedGot != `{"b64":"[REDACTED]","q":"[REDACTED]"}` {
		t.Fatalf("encoded secret: body = %q, want both echoes replaced", encodedGot)
	}
	for _, form := range []string{
		scrubTokenC,
		base64.StdEncoding.EncodeToString([]byte(scrubTokenC)),
		url.QueryEscape(scrubTokenC),
	} {
		if strings.Contains(encodedGot, form) {
			t.Fatalf("encoded secret: body still holds the form %q: %s", form, encodedGot)
		}
	}

	emptyBody := `{"x":"y"}`
	emptyUpstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, emptyBody)
	}))
	t.Cleanup(emptyUpstream.Close)

	emptyRec := callGenericFlow(t, testHandler(), bearerCredential(emptyUpstream.URL, ""), "")
	if got := emptyRec.Body.String(); got != emptyBody {
		t.Fatalf("empty secret: body = %q, want it byte for byte %q", got, emptyBody)
	}
	if strings.Contains(emptyRec.Body.String(), "[REDACTED]") {
		t.Fatalf("empty secret: body = %q, want no redaction marker", emptyRec.Body.String())
	}
}
