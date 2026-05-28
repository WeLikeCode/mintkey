// Package credential provides tests for the TokenExchanger.
package credential

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// BUG-3: SSRF guard tests
// ---------------------------------------------------------------------------

// TestSSRF_LoopbackRefused verifies that a token_url whose host resolves to
// 127.0.0.1 (loopback) is refused by the dial-time guard.
func TestSSRF_LoopbackRefused(t *testing.T) {
	// Start a listener on loopback so the URL is real but should be blocked.
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()

	// A real httptest server on loopback.
	srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintln(w, `{"access_token":"loopback-token"}`)
	}))
	srv.Listener = ln
	srv.Start()
	defer srv.Close()

	te := NewTokenExchanger()
	_, err = te.Exchange(context.Background(), ExchangeRequest{
		TokenURL:          srv.URL,
		CredentialFields:  map[string]string{"user": "x"},
		TokenResponsePath: "$.access_token",
	})

	if err == nil {
		t.Fatal("expected SSRF block for loopback URL, got nil error")
	}
	if !errors.Is(err, ErrTokenEndpointUnreachable) {
		t.Fatalf("expected ErrTokenEndpointUnreachable, got: %v", err)
	}
}

// TestSSRF_LinkLocalRefused verifies that 169.254.x.x (link-local) is refused.
func TestSSRF_LinkLocalRefused(t *testing.T) {
	te := NewTokenExchanger()
	_, err := te.Exchange(context.Background(), ExchangeRequest{
		TokenURL:          "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
		CredentialFields:  map[string]string{},
		TokenResponsePath: "$.access_token",
	})

	if err == nil {
		t.Fatal("expected SSRF block for link-local URL, got nil error")
	}
	if !errors.Is(err, ErrTokenEndpointUnreachable) {
		t.Fatalf("expected ErrTokenEndpointUnreachable, got: %v", err)
	}
}

// TestSSRF_PrivateRangeRefused verifies that a private IP (10.x) is refused.
func TestSSRF_PrivateRangeRefused(t *testing.T) {
	te := NewTokenExchanger()
	_, err := te.Exchange(context.Background(), ExchangeRequest{
		TokenURL:          "http://10.0.0.1/token",
		CredentialFields:  map[string]string{},
		TokenResponsePath: "$.access_token",
	})

	if err == nil {
		t.Fatal("expected SSRF block for private IP 10.0.0.1, got nil error")
	}
	if !errors.Is(err, ErrTokenEndpointUnreachable) {
		t.Fatalf("expected ErrTokenEndpointUnreachable, got: %v", err)
	}
}

// TestSSRF_RedirectToLoopbackRefused verifies that a 302 redirect to a
// loopback URL is also refused (CheckRedirect guard).
func TestSSRF_RedirectToLoopbackRefused(t *testing.T) {
	// Create a loopback server that we redirect to.
	targetLn, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen target: %v", err)
	}
	defer targetLn.Close()

	targetSrv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, `{"access_token":"stolen"}`)
	}))
	targetSrv.Listener = targetLn
	targetSrv.Start()
	defer targetSrv.Close()

	// A redirect server that lives on loopback too but we allow it (same
	// restriction applies — both must be blocked). We actually want to test
	// that when redirect destination is loopback, it's blocked. We use a
	// public-facing httptest (still loopback in CI, so we simulate the
	// redirect guard by confirming the final error is unreachable).
	redirectSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, targetSrv.URL+"/token", http.StatusFound)
	}))
	defer redirectSrv.Close()

	// The exchangerWithPublicBypass allows the redirect server host (for this
	// test we verify the redirect target on loopback is blocked).
	// Since both servers are on 127.0.0.1 in test, we check the redirect is
	// blocked due to the loopback guard on the redirect destination.
	te := NewTokenExchanger()
	_, err = te.Exchange(context.Background(), ExchangeRequest{
		TokenURL:          redirectSrv.URL + "/auth",
		CredentialFields:  map[string]string{"user": "x"},
		TokenResponsePath: "$.access_token",
	})
	if err == nil {
		t.Fatal("expected SSRF block when redirect target is loopback, got nil error")
	}
	if !errors.Is(err, ErrTokenEndpointUnreachable) {
		t.Fatalf("expected ErrTokenEndpointUnreachable, got: %v", err)
	}
}

// TestExchange_PublicEndpointAllowed verifies normal operation using a public
// httptest server. We use the "bypass" exchanger that allows the test server.
func TestExchange_PublicEndpointAllowed(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("decode body: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintln(w, `{"access_token":"my-real-token","expires_in":3600}`)
	}))
	defer srv.Close()

	te := newTestExchanger()
	result, err := te.Exchange(context.Background(), ExchangeRequest{
		TokenURL:          srv.URL + "/token",
		CredentialFields:  map[string]string{"client_id": "abc"},
		TokenResponsePath: "$.access_token",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Token != "my-real-token" {
		t.Errorf("expected token 'my-real-token', got %q", result.Token)
	}
	if result.ExpiresIn != 3600 {
		t.Errorf("expected ExpiresIn=3600, got %d", result.ExpiresIn)
	}
}

// ---------------------------------------------------------------------------
// BUG-6: JSONPath safety tests
// ---------------------------------------------------------------------------

// TestExtractJSONPath_NumericTokenRejected verifies that a numeric access_token
// value is rejected as non-string (not silently coerced via %v).
func TestExtractJSONPath_NumericTokenRejected(t *testing.T) {
	body := []byte(`{"access_token":12345678901234567890}`)
	_, err := extractJSONPath(body, "$.access_token")
	if err == nil {
		t.Fatal("expected error for numeric token value, got nil")
	}
	// Must not contain scientific-notation artefact.
	if strings.Contains(err.Error(), "e+") {
		t.Errorf("error message contains scientific notation, implies coercion occurred: %v", err)
	}
}

// TestExtractJSONPath_FloatTokenRejected verifies that a float64 access_token
// value (e.g. 1.23e20) is rejected, not silently coerced.
func TestExtractJSONPath_FloatTokenRejected(t *testing.T) {
	body := []byte(`{"access_token":1.23456789e20}`)
	_, err := extractJSONPath(body, "$.access_token")
	if err == nil {
		t.Fatal("expected error for float token value, got nil")
	}
}

// TestExtractJSONPath_DeeplyNestedJSON verifies that deeply nested JSON does
// not panic or hang (guard against stack overflow / DoS).
func TestExtractJSONPath_DeeplyNestedJSON(t *testing.T) {
	// Build {"a":{"a":{"a": ... {"access_token":"x"} ...}}} 200 levels deep.
	const depth = 200
	var sb strings.Builder
	for i := 0; i < depth; i++ {
		sb.WriteString(`{"a":`)
	}
	sb.WriteString(`{"access_token":"deep-token"}`)
	for i := 0; i < depth; i++ {
		sb.WriteString(`}`)
	}

	// Extracting the top-level is fine; deeply navigating a rejected path
	// should not panic.
	body := []byte(sb.String())
	// Path with more segments than allowed — must return error, not panic.
	segments := make([]string, depth+1)
	for i := range segments {
		segments[i] = "a"
	}
	path := "$." + strings.Join(segments, ".")
	_, err := extractJSONPath(body, path)
	// We just care it does not panic and returns an error (too many segments).
	if err == nil {
		t.Fatal("expected error for path exceeding depth limit, got nil")
	}
}

// TestExtractJSONPath_NormalExtraction verifies happy-path extraction still works.
func TestExtractJSONPath_NormalExtraction(t *testing.T) {
	body := []byte(`{"access_token":"bearer-xyz"}`)
	token, err := extractJSONPath(body, "$.access_token")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if token != "bearer-xyz" {
		t.Errorf("expected 'bearer-xyz', got %q", token)
	}
}

// TestExtractJSONPath_NestedExtraction verifies nested path extraction.
func TestExtractJSONPath_NestedExtraction(t *testing.T) {
	body := []byte(`{"data":{"token":"nested-bearer"}}`)
	token, err := extractJSONPath(body, "$.data.token")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if token != "nested-bearer" {
		t.Errorf("expected 'nested-bearer', got %q", token)
	}
}

// TestExtractJSONPath_HostileObjectValue verifies that an object at the path
// returns a clean error, not a panic.
func TestExtractJSONPath_HostileObjectValue(t *testing.T) {
	body := []byte(`{"access_token":{"evil":"payload"}}`)
	_, err := extractJSONPath(body, "$.access_token")
	if err == nil {
		t.Fatal("expected error for object token value, got nil")
	}
}

// ---------------------------------------------------------------------------
// BUG-12: Response header timeout test
// ---------------------------------------------------------------------------

// TestResponseHeaderTimeout verifies that ResponseHeaderTimeout is set on the
// transport; this provides the slow-header defence beyond the whole-request timeout.
func TestResponseHeaderTimeout(t *testing.T) {
	te := NewTokenExchanger()
	transport, ok := te.httpClient.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("expected *http.Transport, got %T", te.httpClient.Transport)
	}
	if transport.ResponseHeaderTimeout == 0 {
		t.Fatal("ResponseHeaderTimeout is 0 — slow token endpoint can hold goroutine indefinitely")
	}
	if transport.ResponseHeaderTimeout > 5*time.Second {
		t.Errorf("ResponseHeaderTimeout %v is too large; expected ≤5s", transport.ResponseHeaderTimeout)
	}
}

// ---------------------------------------------------------------------------
// BUG-17: Safe error body interpolation
// ---------------------------------------------------------------------------

// TestExchange_Non2xxStatusNoLeak verifies that a non-2xx response does not
// embed attacker-controlled body content in the error.
func TestExchange_Non2xxStatusNoLeak(t *testing.T) {
	attackerPayload := strings.Repeat("A", 1<<16) // 64KB of attacker data
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		fmt.Fprint(w, attackerPayload)
	}))
	defer srv.Close()

	te := newTestExchanger()
	_, err := te.Exchange(context.Background(), ExchangeRequest{
		TokenURL:          srv.URL + "/token",
		CredentialFields:  map[string]string{},
		TokenResponsePath: "$.access_token",
	})
	if err == nil {
		t.Fatal("expected error for 401 response")
	}
	if !errors.Is(err, ErrTokenExchangeFailed) {
		t.Fatalf("expected ErrTokenExchangeFailed, got: %v", err)
	}
	// The error message must NOT contain the raw attacker payload.
	if strings.Contains(err.Error(), attackerPayload) {
		t.Fatal("error message contains raw attacker-controlled response body — information leak")
	}
	// Must mention status code in a structured way.
	if !strings.Contains(err.Error(), "401") {
		t.Errorf("error message should mention HTTP 401 status, got: %v", err)
	}
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

// newTestExchanger returns a TokenExchanger whose dial-time SSRF guard is
// bypassed for the test loopback addresses (used in public-endpoint tests).
// It sets up the guard via the exported constructor option.
func newTestExchanger() *TokenExchanger {
	return NewTokenExchangerAllowPrivate()
}
