// Package jwt_test exercises the JWT verifier stub.
//
// Source: design §10; ADR-0006; ADR-0004; ADR-0014.4; T-1.0.7; T-1.6.1.
package jwt_test

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/jwt"
)

// jwtParams controls every field used by buildJWTFull.
type jwtParams struct {
	kid   string
	iss   string
	sub   string
	aud   any    // string or []string
	tnt   string
	scope string
	exp   int64
}

// buildJWT constructs a minimal EdDSA JWT signed by sigKey.
// Header: {"alg":"EdDSA","typ":"JWT","kid":"k1"}
// Payload: {"iss":"mintkey/broker","sub":"agent_test","aud":["svc_test"],"tnt":"tenant_A","scope":"read","exp":9999999999}
func buildJWT(t *testing.T, sigKey ed25519.PrivateKey) string {
	t.Helper()
	return buildJWTFull(t, sigKey, jwtParams{
		kid:   "k1",
		iss:   "mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_test"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   9999999999,
	})
}

// buildJWTFull constructs an EdDSA JWT from explicit parameters.
func buildJWTFull(t *testing.T, sigKey ed25519.PrivateKey, p jwtParams) string {
	t.Helper()

	headerMap := map[string]any{"alg": "EdDSA", "typ": "JWT"}
	if p.kid != "" {
		headerMap["kid"] = p.kid
	}
	header := base64.RawURLEncoding.EncodeToString(mustMarshal(t, headerMap))

	claimsMap := map[string]any{
		"iss":   p.iss,
		"sub":   p.sub,
		"aud":   p.aud,
		"tnt":   p.tnt,
		"scope": p.scope,
		"exp":   p.exp,
	}
	payload := base64.RawURLEncoding.EncodeToString(mustMarshal(t, claimsMap))

	msg := header + "." + payload
	sig := ed25519.Sign(sigKey, []byte(msg))
	return msg + "." + base64.RawURLEncoding.EncodeToString(sig)
}

func mustMarshal(t *testing.T, v any) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}
	return b
}

// TestVerify_MalformedJWT confirms that a clearly non-JWT string returns a
// *VerifyError with Code == "invalid_format".
func TestVerify_MalformedJWT(t *testing.T) {
	pub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	keys := map[string]ed25519.PublicKey{"k1": pub}

	_, verifyErr := jwt.Verify("not.a.jwt", keys, jwt.VerifyOptions{})
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}

	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "invalid_format" {
		t.Fatalf("expected Code=%q, got %q", "invalid_format", ve.Code)
	}
}

// TestVerify_WrongSignature confirms that a well-formed JWT signed with a
// different key returns *VerifyError with Code == "signature_invalid".
func TestVerify_WrongSignature(t *testing.T) {
	// Key pair the verifier will trust.
	trustedPub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey (trusted): %v", err)
	}

	// Different key pair used to sign the token.
	_, differentPriv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey (different): %v", err)
	}

	tokenStr := buildJWT(t, differentPriv)

	// Verify with the trusted public key — signature will not match.
	keys := map[string]ed25519.PublicKey{"k1": trustedPub}
	_, verifyErr := jwt.Verify(tokenStr, keys, jwt.VerifyOptions{})
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}

	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "signature_invalid" {
		t.Fatalf("expected Code=%q, got %q", "signature_invalid", ve.Code)
	}

	// Sanity check: the token itself is structurally valid (3 dot-separated parts).
	if parts := strings.Split(tokenStr, "."); len(parts) != 3 {
		t.Fatalf("buildJWT produced malformed token: %q", tokenStr)
	}
}

// TestVerify_ExpiredToken confirms that a token with exp in the past returns
// *VerifyError with Code == "token_expired".
func TestVerify_ExpiredToken(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	keys := map[string]ed25519.PublicKey{"k1": pub}

	// exp = 10 seconds ago; outside the 30s clock skew window.
	tokenStr := buildJWTFull(t, priv, jwtParams{
		kid:   "k1",
		iss:   "mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_test"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   time.Now().Unix() - 61, // 61s ago — well past the 30s skew
	})

	_, verifyErr := jwt.Verify(tokenStr, keys, jwt.VerifyOptions{})
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}
	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "token_expired" {
		t.Fatalf("expected Code=%q, got %q", "token_expired", ve.Code)
	}
}

// TestVerify_ClockSkew30s confirms that a token expiring in less than 30s is
// still accepted (clock skew tolerance).
func TestVerify_ClockSkew30s(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	keys := map[string]ed25519.PublicKey{"k1": pub}

	// exp = 25 seconds from now — still in the future, so not expired.
	tokenStr := buildJWTFull(t, priv, jwtParams{
		kid:   "k1",
		iss:   "mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_test"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   time.Now().Unix() + 25,
	})

	claims, err := jwt.Verify(tokenStr, keys, jwt.VerifyOptions{})
	if err != nil {
		t.Fatalf("expected success, got error: %v", err)
	}
	if claims == nil {
		t.Fatal("expected non-nil claims")
	}
}

// TestVerify_WrongIss confirms that a JWT with a wrong iss returns
// *VerifyError with Code == "signature_invalid".
func TestVerify_WrongIss(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	keys := map[string]ed25519.PublicKey{"k1": pub}

	tokenStr := buildJWTFull(t, priv, jwtParams{
		kid:   "k1",
		iss:   "not-mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_test"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   9999999999,
	})

	_, verifyErr := jwt.Verify(tokenStr, keys, jwt.VerifyOptions{})
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}
	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "signature_invalid" {
		t.Fatalf("expected Code=%q, got %q", "signature_invalid", ve.Code)
	}
}

// TestVerify_AudienceMismatch confirms that a JWT whose aud does not contain
// the expected service ID returns *VerifyError with Code == "audience_mismatch".
func TestVerify_AudienceMismatch(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	keys := map[string]ed25519.PublicKey{"k1": pub}

	tokenStr := buildJWTFull(t, priv, jwtParams{
		kid:   "k1",
		iss:   "mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_other"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   9999999999,
	})

	opts := jwt.VerifyOptions{ExpectedServiceID: "svc_correct"}
	_, verifyErr := jwt.Verify(tokenStr, keys, opts)
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}
	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "audience_mismatch" {
		t.Fatalf("expected Code=%q, got %q", "audience_mismatch", ve.Code)
	}
}

// TestVerify_TenantMismatch confirms that a JWT whose tnt does not match
// the expected tenant ID returns *VerifyError with Code == "tenant_mismatch".
func TestVerify_TenantMismatch(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	keys := map[string]ed25519.PublicKey{"k1": pub}

	tokenStr := buildJWTFull(t, priv, jwtParams{
		kid:   "k1",
		iss:   "mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_test"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   9999999999,
	})

	opts := jwt.VerifyOptions{ExpectedTenantID: "tenant_B"}
	_, verifyErr := jwt.Verify(tokenStr, keys, opts)
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}
	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "tenant_mismatch" {
		t.Fatalf("expected Code=%q, got %q", "tenant_mismatch", ve.Code)
	}
}

// TestVerify_ScopeNotGranted confirms that a JWT whose scope does not match
// the expected action returns *VerifyError with Code == "action_not_granted".
func TestVerify_ScopeNotGranted(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	keys := map[string]ed25519.PublicKey{"k1": pub}

	tokenStr := buildJWTFull(t, priv, jwtParams{
		kid:   "k1",
		iss:   "mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_test"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   9999999999,
	})

	opts := jwt.VerifyOptions{ExpectedAction: "write"}
	_, verifyErr := jwt.Verify(tokenStr, keys, opts)
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}
	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "action_not_granted" {
		t.Fatalf("expected Code=%q, got %q", "action_not_granted", ve.Code)
	}
}

// TestVerify_UnknownKID confirms that a JWT whose kid is not in the pubKeys map
// returns *VerifyError with Code == "unknown_kid".
func TestVerify_UnknownKID(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("GenerateKey: %v", err)
	}
	// pubKeys only has "kid_known"; the token will carry "kid_unknown".
	keys := map[string]ed25519.PublicKey{"kid_known": pub}

	tokenStr := buildJWTFull(t, priv, jwtParams{
		kid:   "kid_unknown",
		iss:   "mintkey/broker",
		sub:   "agent_test",
		aud:   []string{"svc_test"},
		tnt:   "tenant_A",
		scope: "read",
		exp:   9999999999,
	})

	_, verifyErr := jwt.Verify(tokenStr, keys, jwt.VerifyOptions{})
	if verifyErr == nil {
		t.Fatal("expected error, got nil")
	}
	var ve *jwt.VerifyError
	if !errors.As(verifyErr, &ve) {
		t.Fatalf("expected *jwt.VerifyError, got %T: %v", verifyErr, verifyErr)
	}
	if ve.Code != "unknown_kid" {
		t.Fatalf("expected Code=%q, got %q", "unknown_kid", ve.Code)
	}
}
