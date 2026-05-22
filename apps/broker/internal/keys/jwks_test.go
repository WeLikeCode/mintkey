package keys_test

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/mintkey/mintkey/services/broker/internal/keys"
)

// Test: JWKS endpoint returns valid JWK Set with correct fields.
// Source: T-1.0.5 acceptance; Req 6 AC9; ADR-0006; design §7.
func TestJWKS_ValidKeySet(t *testing.T) {
	pub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}

	ring := keys.NewKeyRing()
	ring.Add("kid_01TESTKEY00000000000000000", pub)

	h := keys.JWKSHandler(ring)
	req := httptest.NewRequest(http.MethodGet, "/.well-known/jwks.json", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}

	var set struct {
		Keys []map[string]string `json:"keys"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &set); err != nil {
		t.Fatalf("unmarshal JWKS: %v", err)
	}

	if len(set.Keys) != 1 {
		t.Fatalf("len(keys) = %d, want 1", len(set.Keys))
	}

	k := set.Keys[0]
	if k["kty"] != "OKP" {
		t.Errorf("kty = %q, want OKP", k["kty"])
	}
	if k["crv"] != "Ed25519" {
		t.Errorf("crv = %q, want Ed25519", k["crv"])
	}
	if k["use"] != "sig" {
		t.Errorf("use = %q, want sig", k["use"])
	}
	if k["kid"] != "kid_01TESTKEY00000000000000000" {
		t.Errorf("kid = %q, want kid_01TESTKEY00000000000000000", k["kid"])
	}
	if k["x"] == "" {
		t.Error("x (public key) is empty")
	}
}

// Test: Cache-Control header is "public, max-age=300".
// Source: T-1.0.5 acceptance; ADR-0006.
func TestJWKS_CacheControlHeader(t *testing.T) {
	pub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}

	ring := keys.NewKeyRing()
	ring.Add("kid_01TESTKEY00000000000000001", pub)

	h := keys.JWKSHandler(ring)
	req := httptest.NewRequest(http.MethodGet, "/.well-known/jwks.json", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	cc := rec.Header().Get("Cache-Control")
	if cc != "public, max-age=300" {
		t.Errorf("Cache-Control = %q, want %q", cc, "public, max-age=300")
	}
}

// Test: Multiple keys (rotation overlap) all appear in JWKS.
// Source: T-1.0.5 acceptance; design §7 key management.
func TestJWKS_MultipleKeysInRotationOverlap(t *testing.T) {
	ring := keys.NewKeyRing()
	for i := 0; i < 3; i++ {
		pub, _, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			t.Fatal(err)
		}
		kid := "kid_0000000000000000000000000" + string(rune('A'+i))
		ring.Add(kid, pub)
	}

	h := keys.JWKSHandler(ring)
	req := httptest.NewRequest(http.MethodGet, "/.well-known/jwks.json", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	var set struct {
		Keys []map[string]string `json:"keys"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &set); err != nil {
		t.Fatalf("unmarshal JWKS: %v", err)
	}

	if len(set.Keys) != 3 {
		t.Fatalf("len(keys) = %d, want 3 (rotation overlap)", len(set.Keys))
	}
}
