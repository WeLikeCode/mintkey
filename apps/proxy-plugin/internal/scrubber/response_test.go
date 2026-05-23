package scrubber_test

import (
	"bytes"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/scrubber"
)

func makeResponse(statusCode int, headers map[string]string, body string) *http.Response {
	resp := &http.Response{
		StatusCode: statusCode,
		Header:     make(http.Header),
		Body:       io.NopCloser(bytes.NewBufferString(body)),
	}
	for k, v := range headers {
		resp.Header.Set(k, v)
	}
	return resp
}

func TestScrub_StripAuthorizationHeader(t *testing.T) {
	resp := makeResponse(200, map[string]string{"Authorization": "Bearer secret"}, "")
	result := scrubber.Scrub(resp)
	if !result.Detected {
		t.Fatal("expected Detected=true when Authorization header present")
	}
	if got := result.Response.Header.Get("Authorization"); got != "" {
		t.Fatalf("expected Authorization header stripped, got %q", got)
	}
}

func TestScrub_StripCookieHeader(t *testing.T) {
	resp := makeResponse(200, map[string]string{"Cookie": "session=abc"}, "")
	result := scrubber.Scrub(resp)
	if !result.Detected {
		t.Fatal("expected Detected=true when Cookie header present")
	}
	if got := result.Response.Header.Get("Cookie"); got != "" {
		t.Fatalf("expected Cookie header stripped, got %q", got)
	}
}

func TestScrub_StripSetCookieHeader(t *testing.T) {
	resp := makeResponse(200, map[string]string{"Set-Cookie": "token=secret; HttpOnly"}, "")
	result := scrubber.Scrub(resp)
	if !result.Detected {
		t.Fatal("expected Detected=true when Set-Cookie header present")
	}
	if got := result.Response.Header.Get("Set-Cookie"); got != "" {
		t.Fatalf("expected Set-Cookie header stripped, got %q", got)
	}
}

func TestScrub_RedactAPIKeyInBody(t *testing.T) {
	resp := makeResponse(200, nil, `{"status":"ok","api_key":"sk_live_4eC39H"}`)
	result := scrubber.Scrub(resp)
	if !result.Detected {
		t.Fatal("expected Detected=true when api_key value in body")
	}
	body, err := io.ReadAll(result.Response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(body, []byte("sk_live_4eC39H")) {
		t.Fatalf("expected api_key value redacted, got body: %s", body)
	}
}

func TestScrub_RedactJWTInBody(t *testing.T) {
	resp := makeResponse(200, nil, `{"token":"eyJhbGciOiJFZERTQSJ9.payload.sig"}`)
	result := scrubber.Scrub(resp)
	if !result.Detected {
		t.Fatal("expected Detected=true when JWT in body")
	}
	body, err := io.ReadAll(result.Response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(body, []byte("eyJhbGciOiJFZERTQSJ9")) {
		t.Fatalf("expected JWT redacted, got body: %s", body)
	}
}

func TestScrub_CleanResponsePassesThrough(t *testing.T) {
	originalBody := `{"status":"ok"}`
	resp := makeResponse(200, map[string]string{"Content-Type": "application/json"}, originalBody)
	result := scrubber.Scrub(resp)
	if result.Detected {
		t.Fatal("expected Detected=false for clean response")
	}
	body, err := io.ReadAll(result.Response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if string(body) != originalBody {
		t.Fatalf("expected body unchanged %q, got %q", originalBody, string(body))
	}
	if ct := result.Response.Header.Get("Content-Type"); ct != "application/json" {
		t.Fatalf("expected Content-Type preserved, got %q", ct)
	}
}

func TestScrub_Idempotent(t *testing.T) {
	resp := makeResponse(200, map[string]string{"Authorization": "Bearer secret"}, `{"api_key":"sk_live_123"}`)
	result1 := scrubber.Scrub(resp)
	body1, err := io.ReadAll(result1.Response.Body)
	if err != nil {
		t.Fatal(err)
	}

	// Build a second response from the scrubbed output (no forbidden headers remain).
	resp2 := makeResponse(result1.Response.StatusCode, map[string]string{}, string(body1))
	result2 := scrubber.Scrub(resp2)
	body2, err := io.ReadAll(result2.Response.Body)
	if err != nil {
		t.Fatal(err)
	}

	if string(body1) != string(body2) {
		t.Fatalf("idempotency violated:\n  pass1: %s\n  pass2: %s", body1, body2)
	}
}

// PBT: property — scrubbed output has no forbidden headers.
func TestScrub_PropertyNoForbiddenHeadersAfterScrub(t *testing.T) {
	forbidden := []string{"Authorization", "Cookie", "Set-Cookie", "X-Auth-Token", "X-Api-Key"}
	headers := map[string]string{
		"Authorization": "Bearer tok",
		"Cookie":        "s=1",
		"Set-Cookie":    "s=2",
		"X-Auth-Token":  "tok",
		"X-Api-Key":     "key",
		"Content-Type":  "application/json",
	}
	resp := makeResponse(200, headers, "")
	result := scrubber.Scrub(resp)
	for _, h := range forbidden {
		if v := result.Response.Header.Get(h); v != "" {
			t.Errorf("forbidden header %q still present after Scrub: %q", h, v)
		}
	}
	// Non-forbidden header must survive.
	if ct := result.Response.Header.Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type should survive scrub, got %q", ct)
	}
}

// PBT: scrub(scrub(r)) body == scrub(r) body for a body containing all pattern types.
func TestScrub_BodyIdempotentAllPatterns(t *testing.T) {
	rawBody := strings.Join([]string{
		`api_key=sk_live_abc123def456`,
		`{"token":"eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"}`,
		`pk_live_someCredential999`,
	}, "\n")

	resp1 := makeResponse(200, nil, rawBody)
	r1 := scrubber.Scrub(resp1)
	b1, _ := io.ReadAll(r1.Response.Body)

	resp2 := makeResponse(200, nil, string(b1))
	r2 := scrubber.Scrub(resp2)
	b2, _ := io.ReadAll(r2.Response.Body)

	if string(b1) != string(b2) {
		t.Fatalf("body not idempotent:\n  pass1: %s\n  pass2: %s", b1, b2)
	}
}

// Verify that audit event type constant is exported.
func TestScrub_AuditEventConstant(t *testing.T) {
	const want = "proxy.credential_echo_detected"
	if scrubber.AuditEventCredentialEchoDetected != want {
		t.Fatalf("AuditEventCredentialEchoDetected = %q, want %q",
			scrubber.AuditEventCredentialEchoDetected, want)
	}
}
