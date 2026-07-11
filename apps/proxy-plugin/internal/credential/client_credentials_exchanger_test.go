// Package credential provides tests for the client-credentials TokenExchanger.
package credential

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

// TestExchangeClientCredentials_FormBodyBasicHeaderExtract verifies that the
// client-credentials exchange POSTs a form-encoded grant_type=client_credentials
// (+ scope) body with Content-Type application/x-www-form-urlencoded and an
// Authorization: Basic base64(client_id:client_secret) header, and extracts the
// token via $.access_token.
func TestExchangeClientCredentials_FormBodyBasicHeaderExtract(t *testing.T) {
	var (
		gotMethod      string
		gotContentType string
		gotAuth        string
		gotBody        string
	)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotContentType = r.Header.Get("Content-Type")
		gotAuth = r.Header.Get("Authorization")
		b, _ := io.ReadAll(r.Body)
		gotBody = string(b)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintln(w, `{"access_token":"cc-token-abc","expires_in":3600}`)
	}))
	defer srv.Close()

	te := NewTokenExchangerAllowPrivate()
	result, err := te.ExchangeClientCredentials(context.Background(), ClientCredentialsRequest{
		TokenURL:     srv.URL + "/api/oauth/token",
		ClientID:     "my-client-id",
		ClientSecret: "my-client-secret",
		Scope:        "read write",
		// TokenResponsePath deliberately empty → default "$.access_token".
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Token != "cc-token-abc" {
		t.Errorf("token = %q, want %q", result.Token, "cc-token-abc")
	}
	if result.ExpiresIn != 3600 {
		t.Errorf("ExpiresIn = %d, want 3600", result.ExpiresIn)
	}
	if gotMethod != http.MethodPost {
		t.Errorf("method = %q, want POST", gotMethod)
	}
	if gotContentType != "application/x-www-form-urlencoded" {
		t.Errorf("Content-Type = %q, want application/x-www-form-urlencoded", gotContentType)
	}
	// Authorization must be Basic base64(client_id:client_secret).
	wantAuth := "Basic " + base64.StdEncoding.EncodeToString([]byte("my-client-id:my-client-secret"))
	if gotAuth != wantAuth {
		t.Errorf("Authorization = %q, want %q", gotAuth, wantAuth)
	}
	// Body must be form-encoded with grant_type=client_credentials and scope.
	vals, perr := url.ParseQuery(gotBody)
	if perr != nil {
		t.Fatalf("body is not form-encoded: %v (body=%q)", perr, gotBody)
	}
	if got := vals.Get("grant_type"); got != "client_credentials" {
		t.Errorf("grant_type = %q, want client_credentials", got)
	}
	if got := vals.Get("scope"); got != "read write" {
		t.Errorf("scope = %q, want %q", got, "read write")
	}
}

// TestExchangeClientCredentials_ScopeOmittedWhenEmpty verifies that no scope
// field is sent when Scope is empty.
func TestExchangeClientCredentials_ScopeOmittedWhenEmpty(t *testing.T) {
	var gotBody string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		gotBody = string(b)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintln(w, `{"access_token":"no-scope-token"}`)
	}))
	defer srv.Close()

	te := NewTokenExchangerAllowPrivate()
	_, err := te.ExchangeClientCredentials(context.Background(), ClientCredentialsRequest{
		TokenURL:     srv.URL + "/token",
		ClientID:     "cid",
		ClientSecret: "csec",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	vals, _ := url.ParseQuery(gotBody)
	if _, ok := vals["scope"]; ok {
		t.Errorf("scope should be absent when empty; body=%q", gotBody)
	}
}

// TestExchangeClientCredentials_CustomTokenResponsePath verifies a non-default
// token_response_path is honored.
func TestExchangeClientCredentials_CustomTokenResponsePath(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintln(w, `{"data":{"token":"nested-cc-token"}}`)
	}))
	defer srv.Close()

	te := NewTokenExchangerAllowPrivate()
	result, err := te.ExchangeClientCredentials(context.Background(), ClientCredentialsRequest{
		TokenURL:          srv.URL + "/token",
		ClientID:          "cid",
		ClientSecret:      "csec",
		TokenResponsePath: "$.data.token",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Token != "nested-cc-token" {
		t.Errorf("token = %q, want nested-cc-token", result.Token)
	}
}

// TestExchangeClientCredentials_Non2xxTyped verifies a non-2xx status maps to
// ErrTokenExchangeFailed and does not leak the response body.
func TestExchangeClientCredentials_Non2xxTyped(t *testing.T) {
	leak := strings.Repeat("Z", 1<<10)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		fmt.Fprint(w, leak)
	}))
	defer srv.Close()

	te := NewTokenExchangerAllowPrivate()
	_, err := te.ExchangeClientCredentials(context.Background(), ClientCredentialsRequest{
		TokenURL:     srv.URL + "/token",
		ClientID:     "cid",
		ClientSecret: "csec",
	})
	if err == nil {
		t.Fatal("expected error for 401 response, got nil")
	}
	if !errors.Is(err, ErrTokenExchangeFailed) {
		t.Fatalf("expected ErrTokenExchangeFailed, got: %v", err)
	}
	if strings.Contains(err.Error(), leak) {
		t.Fatal("error leaks attacker-controlled response body")
	}
	if !strings.Contains(err.Error(), "401") {
		t.Errorf("error should mention HTTP 401 status, got: %v", err)
	}
}

// TestExchangeClientCredentials_Unreachable verifies connection-refused maps to
// ErrTokenEndpointUnreachable.
func TestExchangeClientCredentials_Unreachable(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close() // port now closed → connection refused

	te := NewTokenExchangerAllowPrivate()
	_, err = te.ExchangeClientCredentials(context.Background(), ClientCredentialsRequest{
		TokenURL:     "http://" + addr + "/token",
		ClientID:     "cid",
		ClientSecret: "csec",
	})
	if err == nil {
		t.Fatal("expected error for connection-refused endpoint, got nil")
	}
	if !errors.Is(err, ErrTokenEndpointUnreachable) {
		t.Fatalf("expected ErrTokenEndpointUnreachable, got: %v", err)
	}
}

// TestExchangeClientCredentials_SSRFBlocked verifies the default (deny-private)
// exchanger blocks a loopback token_url via the SSRF guard.
func TestExchangeClientCredentials_SSRFBlocked(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()
	srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, `{"access_token":"loopback"}`)
	}))
	srv.Listener = ln
	srv.Start()
	defer srv.Close()

	te := NewTokenExchanger() // default guard — must block loopback
	_, err = te.ExchangeClientCredentials(context.Background(), ClientCredentialsRequest{
		TokenURL:     srv.URL,
		ClientID:     "cid",
		ClientSecret: "csec",
	})
	if err == nil {
		t.Fatal("expected SSRF block for loopback URL, got nil error")
	}
	if !errors.Is(err, ErrTokenEndpointUnreachable) {
		t.Fatalf("expected ErrTokenEndpointUnreachable, got: %v", err)
	}
}

// TestExchangeClientCredentials_HonorsPerCredentialTimeout verifies that a
// server slower than the request timeout returns ErrTokenEndpointUnreachable.
func TestExchangeClientCredentials_HonorsPerCredentialTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second)
		fmt.Fprintln(w, `{"access_token":"too-slow"}`)
	}))
	defer srv.Close()

	te := NewTokenExchangerAllowPrivate()
	start := time.Now()
	_, err := te.ExchangeClientCredentials(context.Background(), ClientCredentialsRequest{
		TokenURL:     srv.URL + "/token",
		ClientID:     "cid",
		ClientSecret: "csec",
		Timeout:      500 * time.Millisecond,
	})
	elapsed := time.Since(start)
	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}
	if !errors.Is(err, ErrTokenEndpointUnreachable) {
		t.Fatalf("expected ErrTokenEndpointUnreachable, got: %v", err)
	}
	if elapsed > 1500*time.Millisecond {
		t.Errorf("exchange took %v, expected to time out near 500ms", elapsed)
	}
}
