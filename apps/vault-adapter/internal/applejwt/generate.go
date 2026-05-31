// Package applejwt generates signed ES256 JWTs for Apple's App Store Connect API.
// See: https://developer.apple.com/documentation/appstoreconnectapi/generating_tokens_for_api_requests
//
// Security note: this package never logs or persists key material.
// Caller is responsible for zeroizing p8KeyPEM bytes after calling Generate.
package applejwt

import (
	"crypto/ecdsa"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"time"

	"github.com/go-jose/go-jose/v4"
	"github.com/go-jose/go-jose/v4/jwt"
)

const (
	// AudienceAppStoreConnect is the fixed audience value required by Apple's
	// App Store Connect API. Must appear verbatim in every generated JWT.
	AudienceAppStoreConnect = "appstoreconnect-v1"

	// tokenTTL is the lifetime of a generated JWT. Apple enforces a 20-minute
	// hard maximum; we use 19 minutes to provide a 1-minute clock-skew buffer.
	tokenTTL = 19 * time.Minute
)

// Generate produces a signed ES256 JWT suitable for the App Store Connect API.
//
// p8KeyPEM must be a PKCS#8 PEM-encoded EC private key (the contents of the
// .p8 file downloaded from App Store Connect).
// keyID is the 10-character Key ID shown in the Apple Developer portal.
// issuerID is the UUID Issuer ID shown in App Store Connect → Users and Access → Keys.
//
// The returned string is the compact JWS serialization (three Base64url segments
// separated by dots). The JWT carries:
//   - alg: ES256
//   - kid: keyID  (JOSE header)
//   - iss: issuerID
//   - iat: current Unix time
//   - exp: iat + 19 minutes  (Apple max is 20 minutes; 1-minute buffer)
//   - aud: ["appstoreconnect-v1"]
//
// Caller is responsible for zeroizing p8KeyPEM bytes after this call.
func Generate(p8KeyPEM []byte, keyID, issuerID string) (string, error) {
	block, _ := pem.Decode(p8KeyPEM)
	if block == nil {
		return "", fmt.Errorf("applejwt: failed to decode PEM block from input")
	}

	rawKey, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return "", fmt.Errorf("applejwt: parse PKCS8 private key: %w", err)
	}

	ecKey, ok := rawKey.(*ecdsa.PrivateKey)
	if !ok {
		return "", fmt.Errorf("applejwt: expected EC private key (*ecdsa.PrivateKey), got %T", rawKey)
	}

	sig, err := jose.NewSigner(
		jose.SigningKey{Algorithm: jose.ES256, Key: ecKey},
		(&jose.SignerOptions{}).WithType("JWT").WithHeader("kid", keyID),
	)
	if err != nil {
		return "", fmt.Errorf("applejwt: new signer: %w", err)
	}

	now := time.Now()
	claims := jwt.Claims{
		Issuer:   issuerID,
		IssuedAt: jwt.NewNumericDate(now),
		Expiry:   jwt.NewNumericDate(now.Add(tokenTTL)),
		Audience: jwt.Audience{AudienceAppStoreConnect},
	}

	return jwt.Signed(sig).Claims(claims).Serialize()
}
