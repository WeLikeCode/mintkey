package googleserviceaccount

import (
	"context"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/go-jose/go-jose/v4"
	josejwt "github.com/go-jose/go-jose/v4/jwt"
)

// httpClient is the package-level HTTP client used for all token requests.
// Using a dedicated client (not http.DefaultClient) avoids shared-transport
// interference and enforces an explicit timeout per spec §8.
var httpClient = &http.Client{Timeout: 10 * time.Second}

// TokenResponse holds the fields returned by the Google OAuth2 token endpoint.
type TokenResponse struct {
	AccessToken string `json:"access_token"`
	ExpiresIn   int    `json:"expires_in"`
	TokenType   string `json:"token_type"`
}

// FetchAccessToken signs a JWT assertion with the service account's RSA private
// key and exchanges it at key.TokenURI for a Google OAuth2 access token.
//
// Key material handling:
//   - The PEM block is decoded; PKCS8 is tried first, PKCS1 is the fallback
//     (older Google-issued keys use RSA PRIVATE KEY / PKCS1).
//   - Only RSA keys are accepted; EC keys return a descriptive error.
func FetchAccessToken(ctx context.Context, key *KeyFile, scope string) (*TokenResponse, error) {
	rsaKey, err := parseRSAPrivateKey(key.PrivateKey)
	if err != nil {
		return nil, err
	}

	sig, err := jose.NewSigner(
		jose.SigningKey{Algorithm: jose.RS256, Key: rsaKey},
		(&jose.SignerOptions{}).WithHeader("kid", key.PrivateKeyID),
	)
	if err != nil {
		return nil, fmt.Errorf("googleserviceaccount: create signer: %w", err)
	}

	now := time.Now()
	claims := josejwt.Claims{
		Issuer:   key.ClientEmail,
		Subject:  key.ClientEmail,
		Audience: josejwt.Audience{key.TokenURI},
		IssuedAt: josejwt.NewNumericDate(now),
		Expiry:   josejwt.NewNumericDate(now.Add(60 * time.Second)),
	}

	// Google requires a non-standard "scope" claim in the JWT assertion.
	// go-jose's Claims() accepts map[string]interface{} or structs only.
	extraClaims := map[string]interface{}{"scope": scope}

	raw, err := josejwt.Signed(sig).Claims(claims).Claims(extraClaims).Serialize()
	if err != nil {
		return nil, fmt.Errorf("googleserviceaccount: serialize JWT: %w", err)
	}

	formBody := url.Values{
		"grant_type": {"urn:ietf:params:oauth:grant-type:jwt-bearer"},
		"assertion":  {raw},
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, key.TokenURI,
		strings.NewReader(formBody.Encode()))
	if err != nil {
		return nil, fmt.Errorf("googleserviceaccount: build token request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("googleserviceaccount: token request: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("googleserviceaccount: token endpoint returned %d: %s",
			resp.StatusCode, string(body))
	}

	var tr TokenResponse
	if err := json.Unmarshal(body, &tr); err != nil {
		return nil, fmt.Errorf("googleserviceaccount: decode token response: %w", err)
	}
	return &tr, nil
}

// parseRSAPrivateKey decodes a PEM-encoded RSA private key.
// PKCS8 ("PRIVATE KEY") is tried first; PKCS1 ("RSA PRIVATE KEY") is the
// fallback for older Google-issued key files.
func parseRSAPrivateKey(pemStr string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemStr))
	if block == nil {
		return nil, fmt.Errorf("googleserviceaccount: private_key is not valid PEM")
	}

	// Attempt PKCS8 first.
	if block.Type == "PRIVATE KEY" {
		key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("googleserviceaccount: parse PKCS8 key: %w", err)
		}
		rsaKey, ok := key.(*rsa.PrivateKey)
		if !ok {
			return nil, fmt.Errorf("googleserviceaccount: expected RSA private key, got %T", key)
		}
		return rsaKey, nil
	}

	// Fallback: PKCS1.
	if block.Type == "RSA PRIVATE KEY" {
		rsaKey, err := x509.ParsePKCS1PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("googleserviceaccount: parse PKCS1 key: %w", err)
		}
		return rsaKey, nil
	}

	return nil, fmt.Errorf("googleserviceaccount: unsupported PEM block type %q; expected \"PRIVATE KEY\" (PKCS8) or \"RSA PRIVATE KEY\" (PKCS1)", block.Type)
}
