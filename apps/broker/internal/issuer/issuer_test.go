package issuer_test

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/broker/internal/issuer"
	"github.com/mintkey/mintkey/services/broker/internal/keys"
)

// parseJWT decodes the header and claims of a compact JWS token.
func parseJWT(t *testing.T, token string) (header map[string]any, claims map[string]any) {
	t.Helper()
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Fatalf("invalid JWT: expected 3 parts, got %d", len(parts))
	}
	hBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		t.Fatalf("decode header: %v", err)
	}
	cBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		t.Fatalf("decode claims: %v", err)
	}
	if err := json.Unmarshal(hBytes, &header); err != nil {
		t.Fatalf("unmarshal header: %v", err)
	}
	if err := json.Unmarshal(cBytes, &claims); err != nil {
		t.Fatalf("unmarshal claims: %v", err)
	}
	return
}

// verifyJWT checks the Ed25519 signature on token using pub.
func verifyJWT(t *testing.T, token string, pub ed25519.PublicKey) {
	t.Helper()
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Fatal("invalid JWT for verification")
	}
	signingInput := []byte(parts[0] + "." + parts[1])
	sig, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		t.Fatalf("decode signature: %v", err)
	}
	if !ed25519.Verify(pub, signingInput, sig) {
		t.Error("JWT signature verification failed")
	}
}

// TestIssuedJWT_HasCorrectClaims asserts all required claims and header fields.
// Sources: ADR-0006, ADR-0008, ADR-0017.11, T-1.5.3.
func TestIssuedJWT_HasCorrectClaims(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ring := keys.NewKeyRing()
	kid := "kid_01TESTULID0000000000000000"
	ring.Add(kid, pub)

	iss := issuer.New(priv, kid, ring)
	before := time.Now().Unix()
	token, err := iss.Issue(issuer.TokenRequest{
		AgentID:    "agent_01HX00000000000000000000AA",
		ServiceID:  "svc_01HX00000000000000000000BB",
		TenantID:   "tenant_01HX00000000000000000000CC",
		Scope:      "read",
		TTLSeconds: 300,
	})
	after := time.Now().Unix()
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}

	header, claims := parseJWT(t, token)

	// Header assertions
	if header["alg"] != "EdDSA" {
		t.Errorf("alg = %v, want EdDSA", header["alg"])
	}
	if header["typ"] != "JWT" {
		t.Errorf("typ = %v, want JWT", header["typ"])
	}
	if header["kid"] != kid {
		t.Errorf("kid = %v, want %s", header["kid"], kid)
	}

	// Claim: iss
	if claims["iss"] != "mintkey/broker" {
		t.Errorf("iss = %v, want mintkey/broker", claims["iss"])
	}
	// Claim: sub
	if claims["sub"] != "agent_01HX00000000000000000000AA" {
		t.Errorf("sub = %v, want agent_01HX...", claims["sub"])
	}
	// Claim: aud (JSON numbers unmarshal as float64; aud is []string)
	aud, ok := claims["aud"].([]any)
	if !ok || len(aud) != 1 || aud[0] != "svc_01HX00000000000000000000BB" {
		t.Errorf("aud = %v, want [svc_01HX...]", claims["aud"])
	}
	// Claim: tnt — must be prefixed ULID, not slug
	if claims["tnt"] != "tenant_01HX00000000000000000000CC" {
		t.Errorf("tnt = %v, want tenant_01HX...", claims["tnt"])
	}
	// Claim: scope
	if claims["scope"] != "read" {
		t.Errorf("scope = %v, want read", claims["scope"])
	}
	// Claim: jti starts with "jti_"
	jti, _ := claims["jti"].(string)
	if !strings.HasPrefix(jti, "jti_") {
		t.Errorf("jti = %q, want prefix jti_", jti)
	}
	// Claim: iat / exp timing
	iat, _ := claims["iat"].(float64)
	exp, _ := claims["exp"].(float64)
	if int64(iat) < before || int64(iat) > after {
		t.Errorf("iat %v not in [%d, %d]", iat, before, after)
	}
	if int64(exp) != int64(iat)+300 {
		t.Errorf("exp = %v, want iat+300 = %v", exp, int64(iat)+300)
	}
}

// TestIssuedJWT_SignatureVerifies checks the Ed25519 signature is valid.
// Sources: ADR-0006, T-1.5.3.
func TestIssuedJWT_SignatureVerifies(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ring := keys.NewKeyRing()
	kid := "kid_01TESTULID0000000000000001"
	ring.Add(kid, pub)

	iss := issuer.New(priv, kid, ring)
	token, err := iss.Issue(issuer.TokenRequest{
		AgentID:    "agent_01HX00000000000000000000AA",
		ServiceID:  "svc_01HX00000000000000000000BB",
		TenantID:   "tenant_01HX00000000000000000000CC",
		Scope:      "write",
		TTLSeconds: 600,
	})
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}

	verifyJWT(t, token, pub)
}

// TestJTI_IsUnique issues 100 JWTs and asserts all jti values are distinct.
// Sources: ADR-0006, T-1.5.3.
func TestJTI_IsUnique(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ring := keys.NewKeyRing()
	kid := "kid_01TESTULID0000000000000002"
	ring.Add(kid, pub)

	iss := issuer.New(priv, kid, ring)
	seen := make(map[string]struct{}, 100)
	for n := 0; n < 100; n++ {
		token, err := iss.Issue(issuer.TokenRequest{
			AgentID:    "agent_01HX00000000000000000000AA",
			ServiceID:  "svc_01HX00000000000000000000BB",
			TenantID:   "tenant_01HX00000000000000000000CC",
			Scope:      "read",
			TTLSeconds: 60,
		})
		if err != nil {
			t.Fatalf("Issue #%d: %v", n, err)
		}
		_, claims := parseJWT(t, token)
		jti, _ := claims["jti"].(string)
		if _, dup := seen[jti]; dup {
			t.Fatalf("duplicate jti %q at iteration %d", jti, n)
		}
		seen[jti] = struct{}{}
	}
}

// TestTNT_IsPrefixedULID_NotSlug asserts tnt is the prefixed ULID, not a slug.
// Sources: ADR-0008, ADR-0017.11, ADR-0017.9, T-1.5.3.
func TestTNT_IsPrefixedULID_NotSlug(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ring := keys.NewKeyRing()
	kid := "kid_01TESTULID0000000000000003"
	ring.Add(kid, pub)

	iss := issuer.New(priv, kid, ring)
	token, err := iss.Issue(issuer.TokenRequest{
		AgentID:    "agent_01HX00000000000000000000AA",
		ServiceID:  "svc_01HX00000000000000000000BB",
		TenantID:   "tenant_01HX00000000000000000000CC",
		Scope:      "read",
		TTLSeconds: 60,
	})
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}

	_, claims := parseJWT(t, token)
	tnt, _ := claims["tnt"].(string)

	if !strings.HasPrefix(tnt, "tenant_") {
		t.Errorf("tnt = %q: must start with tenant_ (prefixed ULID)", tnt)
	}
	// Explicitly guard against slug forms (ADR-0017.9: default slug is t_default)
	if tnt == "t_default" || tnt == "default" {
		t.Errorf("tnt = %q: must be prefixed ULID, not a slug", tnt)
	}
	if tnt != "tenant_01HX00000000000000000000CC" {
		t.Errorf("tnt = %q, want tenant_01HX00000000000000000000CC", tnt)
	}
}
