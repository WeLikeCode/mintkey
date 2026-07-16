package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// buildTestJWTWithScope creates a signed test JWT with an explicit scope claim.
// The returned public key must be loaded into handler.pubKeys["testkey"].
func buildTestJWTWithScope(t *testing.T, audUUID, scope string) (string, ed25519.PublicKey) {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	headerMap := map[string]any{"alg": "EdDSA", "typ": "JWT", "kid": "testkey"}
	header := base64.RawURLEncoding.EncodeToString(mustMarshalJSON(t, headerMap))
	claimsMap := map[string]any{
		"iss":   "mintkey/broker",
		"sub":   "agent_test",
		"aud":   []string{audUUID},
		"tnt":   "tenant-test-uuid-0001",
		"scope": scope,
		"exp":   time.Now().Unix() + 600,
	}
	payload := base64.RawURLEncoding.EncodeToString(mustMarshalJSON(t, claimsMap))
	msg := header + "." + payload
	sig := ed25519.Sign(priv, []byte(msg))
	return msg + "." + base64.RawURLEncoding.EncodeToString(sig), pub
}

// TestReadAtlasGate verifies the read-scoped method gate: a read:atlas token may
// only use safe HTTP methods (GET/HEAD/OPTIONS). A read:atlas write is denied with
// 403 before the vault credential fetch (so the credential is never touched); every
// other scope — admin:atlas, call, email, … — is unaffected regardless of method.
//
// Assertion strategy: the gate returns 403 with the message
// "read:atlas grants read-only access". A request that PASSES the gate proceeds to
// the vault fetch, which is unreachable (localhost:1) and therefore returns 502 —
// never 403. So "403 + gate message" proves the gate fired before the vault, and
// "not 403" proves the request passed the gate and reached the credential path.
func TestReadAtlasGate(t *testing.T) {
	cases := []struct {
		name       string
		scope      string
		method     string
		wantDenied bool
	}{
		{"read:atlas DELETE denied", "read:atlas", http.MethodDelete, true},
		{"read:atlas GET allowed", "read:atlas", http.MethodGet, false},
		{"admin:atlas DELETE allowed", "admin:atlas", http.MethodDelete, false},
		{"call DELETE unaffected", "call", http.MethodDelete, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := testHandler() // permissive; vault at localhost:1 (unreachable)
			token, pub := buildTestJWTWithScope(t, testSvcUUIDA, tc.scope)
			h.pubKeys["testkey"] = pub

			// URL "/" carries no UUID segment → the aud check is skipped, isolating
			// the read:atlas gate under test.
			req := httptest.NewRequest(tc.method, "/", nil)
			req.Header.Set("Authorization", "Bearer "+token)
			rw := httptest.NewRecorder()
			h.ServeHTTP(rw, req)

			if tc.wantDenied {
				if rw.Code != http.StatusForbidden {
					t.Fatalf("expected 403 (gate blocks write, never reaches vault), got %d (body: %s)", rw.Code, rw.Body.String())
				}
				if !strings.Contains(rw.Body.String(), "read:atlas") {
					t.Fatalf("expected read:atlas gate message, got: %s", rw.Body.String())
				}
				// The gate must fire BEFORE the vault fetch: a vault failure is 502
				// with a "vault" message, never this 403 gate body.
				if strings.Contains(rw.Body.String(), "vault") {
					t.Fatalf("denied request reached the vault path; body: %s", rw.Body.String())
				}
			} else {
				if rw.Code == http.StatusForbidden {
					t.Fatalf("gate must NOT fire for scope=%q method=%q; got 403 (body: %s)", tc.scope, tc.method, rw.Body.String())
				}
			}
		})
	}
}
