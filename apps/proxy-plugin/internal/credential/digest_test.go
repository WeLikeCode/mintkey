package credential

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"strings"
	"testing"

	"github.com/icholy/digest"
)

const (
	testDigestPublicKey  = "atlas-public-key"
	testDigestPrivateKey = "atlas-private-key"
	testDigestRealm      = "atlas"
	testDigestNonce      = "dcd98b7102dd2f0e8b11d0f600bfb0c093"
)

// digestChallengeServer stands up an httptest server that issues a
// WWW-Authenticate: Digest challenge on the first request and, on the second,
// validates the client's Digest Authorization against the known key pair.
// It records the Authorization header seen on each hit so tests can assert the
// agent-supplied header never survives.
func digestChallengeServer(t *testing.T, seen *[]string) *httptest.Server {
	t.Helper()
	var calls int
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		*seen = append(*seen, r.Header.Get("Authorization"))
		if calls == 1 {
			w.Header().Set("WWW-Authenticate",
				fmt.Sprintf(`Digest realm=%q, nonce=%q, qop="auth", algorithm=MD5`,
					testDigestRealm, testDigestNonce))
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		auth := r.Header.Get("Authorization")
		got, err := digest.ParseCredentials(auth)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		// Recompute the expected response from the SERVER-side known password and
		// the client-chosen cnonce/nc; a match proves the digest was computed from
		// the stored key pair.
		chal := &digest.Challenge{
			Realm:     testDigestRealm,
			Nonce:     testDigestNonce,
			Algorithm: "MD5",
			QOP:       []string{"auth"},
		}
		want, err := digest.Digest(chal, digest.Options{
			Method:   r.Method,
			URI:      got.URI,
			Count:    got.Nc,
			Cnonce:   got.Cnonce,
			Username: testDigestPublicKey,
			Password: testDigestPrivateKey,
		})
		if err != nil || want.Response != got.Response {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, "ok")
	}))
}

// TestNewDigestTransport_CompletesHandshakeAndStripsAgentAuth mirrors the
// production composition in cmd/proxy-plugin/main.go (handleHTTPDigest): a
// reverse proxy whose Director strips the agent Authorization and whose
// Transport is the per-request digest.Transport. It asserts the upstream never
// sees the agent's Bearer, the challenge is answered with a valid Digest
// Authorization computed from the key pair, and the call succeeds.
func TestNewDigestTransport_CompletesHandshakeAndStripsAgentAuth(t *testing.T) {
	var seen []string
	upstream := digestChallengeServer(t, &seen)
	defer upstream.Close()

	payload := []byte(fmt.Sprintf(`{"public_key":%q,"private_key":%q}`,
		testDigestPublicKey, testDigestPrivateKey))
	dt, err := NewDigestTransport(payload, nil)
	if err != nil {
		t.Fatalf("NewDigestTransport: unexpected error: %v", err)
	}

	target, err := url.Parse(upstream.URL)
	if err != nil {
		t.Fatalf("parse upstream URL: %v", err)
	}
	proxy := httputil.NewSingleHostReverseProxy(target)
	proxy.Transport = dt
	orig := proxy.Director
	proxy.Director = func(req *http.Request) {
		orig(req)
		req.Header.Del("Authorization") // mirrors main.go handleHTTPDigest Director
	}

	req := httptest.NewRequest(http.MethodGet, "/groups", nil)
	req.Header.Set("Authorization", "Bearer agent-jwt-should-be-stripped")
	rec := httptest.NewRecorder()
	proxy.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 after digest handshake, got %d (body=%q)", rec.Code, rec.Body.String())
	}
	if len(seen) != 2 {
		t.Fatalf("expected 2 upstream hits (challenge + authenticated), got %d", len(seen))
	}
	// Challenge phase: agent Authorization must have been stripped by the Director.
	if seen[0] != "" {
		t.Fatalf("challenge request carried an Authorization header (agent auth not stripped): %q", seen[0])
	}
	// Authenticated phase: must be a Digest header with the public_key username,
	// and must not contain the agent's Bearer token.
	if !strings.HasPrefix(seen[1], "Digest ") {
		t.Fatalf("authenticated request Authorization is not Digest: %q", seen[1])
	}
	if !strings.Contains(seen[1], `username="`+testDigestPublicKey+`"`) {
		t.Fatalf("Digest Authorization missing public_key username: %q", seen[1])
	}
	if strings.Contains(seen[1], "agent-jwt") {
		t.Fatalf("agent Bearer token leaked into upstream Authorization: %q", seen[1])
	}
}

// TestNewDigestTransport_RejectsInvalidPayloads verifies the parser rejects
// malformed / incomplete payloads and never echoes submitted key material.
func TestNewDigestTransport_RejectsInvalidPayloads(t *testing.T) {
	cases := []struct {
		name    string
		payload string
		secret  string // material that MUST NOT appear in the error
	}{
		{"empty private key", `{"public_key":"pub","private_key":""}`, ""},
		{"empty public key", `{"public_key":"","private_key":"super-secret-priv"}`, "super-secret-priv"},
		{"not json", `super-secret-priv`, "super-secret-priv"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			dt, err := NewDigestTransport([]byte(tc.payload), nil)
			if err == nil {
				t.Fatalf("expected error for %s, got transport %+v", tc.name, dt)
			}
			if tc.secret != "" && strings.Contains(err.Error(), tc.secret) {
				t.Fatalf("error message leaked credential material: %q", err.Error())
			}
		})
	}
}
