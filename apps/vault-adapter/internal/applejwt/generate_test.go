package applejwt_test

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"strings"
	"testing"
	"time"

	"github.com/go-jose/go-jose/v4"
	josejwt "github.com/go-jose/go-jose/v4/jwt"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/applejwt"
)

// mustECKeyPEM generates a P-256 ECDSA key and returns it PEM-encoded as PKCS#8.
func mustECKeyPEM(t *testing.T) ([]byte, *ecdsa.PrivateKey) {
	t.Helper()
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate EC key: %v", err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		t.Fatalf("marshal PKCS8: %v", err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
	return pemBytes, priv
}

// mustRSAKeyPEM generates a 2048-bit RSA key and returns it PEM-encoded as PKCS#8.
func mustRSAKeyPEM(t *testing.T) []byte {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate RSA key: %v", err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		t.Fatalf("marshal PKCS8: %v", err)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
}

// TestGenerate_HappyPath verifies that a well-formed JWT is produced with the
// expected algorithm, headers, and claims.
func TestGenerate_HappyPath(t *testing.T) {
	pemBytes, ecPriv := mustECKeyPEM(t)

	const keyID = "TESTKEY1234"
	const issuerID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

	token, err := applejwt.Generate(pemBytes, keyID, issuerID)
	if err != nil {
		t.Fatalf("Generate returned unexpected error: %v", err)
	}
	if token == "" {
		t.Fatal("Generate returned empty token")
	}

	// Parse the compact JWS so we can inspect headers and claims without
	// trusting the library to set them correctly by default.
	parsedJWT, err := josejwt.ParseSigned(token, []jose.SignatureAlgorithm{jose.ES256})
	if err != nil {
		t.Fatalf("ParseSigned: %v", err)
	}

	// --- Header checks ---
	if len(parsedJWT.Headers) == 0 {
		t.Fatal("no JOSE headers in parsed JWT")
	}
	hdr := parsedJWT.Headers[0]

	if hdr.Algorithm != string(jose.ES256) {
		t.Errorf("alg = %q, want %q", hdr.Algorithm, string(jose.ES256))
	}

	// go-jose surfaces the standard "kid" header field via hdr.KeyID, not
	// ExtraHeaders — the JOSE spec defines kid as a registered header parameter.
	if hdr.KeyID != keyID {
		t.Errorf("kid = %q, want %q", hdr.KeyID, keyID)
	}

	// --- Claims (signature-verified) ---
	var claims josejwt.Claims
	if err := parsedJWT.Claims(ecPriv.Public(), &claims); err != nil {
		t.Fatalf("verify+extract claims: %v", err)
	}

	if claims.Issuer != issuerID {
		t.Errorf("iss = %q, want %q", claims.Issuer, issuerID)
	}

	if len(claims.Audience) != 1 || claims.Audience[0] != applejwt.AudienceAppStoreConnect {
		t.Errorf("aud = %v, want [%q]", claims.Audience, applejwt.AudienceAppStoreConnect)
	}

	if claims.IssuedAt == nil || claims.Expiry == nil {
		t.Fatal("iat or exp is nil")
	}

	iat := claims.IssuedAt.Time()
	exp := claims.Expiry.Time()
	ttl := exp.Sub(iat)

	if ttl != 19*time.Minute {
		t.Errorf("exp-iat = %v, want exactly 19m", ttl)
	}
}

// TestGenerate_BadPEM ensures passing non-PEM bytes returns an error without
// panicking, and the error message references PEM decoding.
func TestGenerate_BadPEM(t *testing.T) {
	_, err := applejwt.Generate([]byte("not a PEM block at all"), "K1", "iss1")
	if err == nil {
		t.Fatal("expected error for bad PEM input, got nil")
	}
	if !strings.Contains(strings.ToLower(err.Error()), "pem") {
		t.Errorf("error message %q does not mention PEM", err.Error())
	}
}

// TestGenerate_NonECKey verifies that an RSA PKCS#8 key is rejected with a
// descriptive error that mentions EC/ecdsa.
func TestGenerate_NonECKey(t *testing.T) {
	rsaPEM := mustRSAKeyPEM(t)
	_, err := applejwt.Generate(rsaPEM, "K1", "iss1")
	if err == nil {
		t.Fatal("expected error for RSA key, got nil")
	}
	msg := strings.ToLower(err.Error())
	if !strings.Contains(msg, "ec") && !strings.Contains(msg, "ecdsa") {
		t.Errorf("error %q does not mention EC/ecdsa", err.Error())
	}
}

// TestGenerate_StrictTTL ensures the generated token lifetime is strictly less
// than 20 minutes (Apple's hard maximum).
func TestGenerate_StrictTTL(t *testing.T) {
	pemBytes, ecPriv := mustECKeyPEM(t)

	token, err := applejwt.Generate(pemBytes, "K1", "iss1")
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}

	parsedJWT, err := josejwt.ParseSigned(token, []jose.SignatureAlgorithm{jose.ES256})
	if err != nil {
		t.Fatalf("ParseSigned: %v", err)
	}

	var claims josejwt.Claims
	if err := parsedJWT.Claims(ecPriv.Public(), &claims); err != nil {
		t.Fatalf("verify+extract claims: %v", err)
	}

	if claims.IssuedAt == nil || claims.Expiry == nil {
		t.Fatal("iat or exp is nil")
	}

	ttl := claims.Expiry.Time().Sub(claims.IssuedAt.Time())
	if ttl >= 20*time.Minute {
		t.Errorf("TTL %v is >= Apple's 20-minute maximum — token would be rejected", ttl)
	}
}

// TestAudienceConstant verifies the package-level AudienceAppStoreConnect
// constant has the exact string value required by Apple.
func TestAudienceConstant(t *testing.T) {
	const want = "appstoreconnect-v1"
	if applejwt.AudienceAppStoreConnect != want {
		t.Errorf("AudienceAppStoreConnect = %q, want %q",
			applejwt.AudienceAppStoreConnect, want)
	}

	// Also assert the decoded claim matches the constant (not a separate literal).
	pemBytes, ecPriv := mustECKeyPEM(t)
	token, err := applejwt.Generate(pemBytes, "K1", "iss1")
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	parsedJWT, err := josejwt.ParseSigned(token, []jose.SignatureAlgorithm{jose.ES256})
	if err != nil {
		t.Fatalf("ParseSigned: %v", err)
	}
	var claims josejwt.Claims
	if err := parsedJWT.Claims(ecPriv.Public(), &claims); err != nil {
		t.Fatalf("verify+extract claims: %v", err)
	}
	if len(claims.Audience) != 1 || claims.Audience[0] != applejwt.AudienceAppStoreConnect {
		t.Errorf("decoded aud %v does not match AudienceAppStoreConnect %q",
			claims.Audience, applejwt.AudienceAppStoreConnect)
	}
}
