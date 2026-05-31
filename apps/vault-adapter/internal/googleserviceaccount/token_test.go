package googleserviceaccount

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/go-jose/go-jose/v4"
	josejwt "github.com/go-jose/go-jose/v4/jwt"
)

// makeRSAKeyPEM generates an RSA-2048 key and returns (privateKey, PKCS8-PEM-string).
func makeRSAKeyPEM(t *testing.T) (*rsa.PrivateKey, string) {
	t.Helper()
	privKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate RSA key: %v", err)
	}
	pkcs8Bytes, err := x509.MarshalPKCS8PrivateKey(privKey)
	if err != nil {
		t.Fatalf("marshal PKCS8: %v", err)
	}
	pemBlock := pem.EncodeToMemory(&pem.Block{
		Type:  "PRIVATE KEY",
		Bytes: pkcs8Bytes,
	})
	return privKey, string(pemBlock)
}

// TestFetchAccessToken_HappyPath verifies the full JWT-bearer exchange:
//   - httptest server asserts Content-Type, parses form body, verifies JWS
//     signature with the real RSA public key, checks iss and scope claims.
//   - FetchAccessToken returns the token from the server's JSON response.
func TestFetchAccessToken_HappyPath(t *testing.T) {
	privKey, pemStr := makeRSAKeyPEM(t)

	var serverURL string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Assert Content-Type.
		ct := r.Header.Get("Content-Type")
		if ct != "application/x-www-form-urlencoded" {
			t.Errorf("Content-Type: got %q, want application/x-www-form-urlencoded", ct)
		}

		if err := r.ParseForm(); err != nil {
			t.Errorf("parse form: %v", err)
		}
		grantType := r.FormValue("grant_type")
		if grantType != "urn:ietf:params:oauth:grant-type:jwt-bearer" {
			t.Errorf("grant_type: got %q", grantType)
		}

		rawJWS := r.FormValue("assertion")
		if rawJWS == "" {
			t.Error("assertion field is empty")
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}

		// Parse and verify JWS.
		tok, err := josejwt.ParseSigned(rawJWS, []jose.SignatureAlgorithm{jose.RS256})
		if err != nil {
			t.Errorf("parse signed JWT: %v", err)
			http.Error(w, "bad jwt", http.StatusBadRequest)
			return
		}

		var claims map[string]interface{}
		if err := tok.Claims(privKey.Public(), &claims); err != nil {
			t.Errorf("verify JWT signature: %v", err)
			http.Error(w, "sig verify failed", http.StatusUnauthorized)
			return
		}

		// Verify iss.
		if iss, _ := claims["iss"].(string); iss != "sa@test-project.iam.gserviceaccount.com" {
			t.Errorf("iss: got %q", iss)
		}
		// Verify scope.
		if scope, _ := claims["scope"].(string); scope != "https://www.googleapis.com/auth/cloud-platform" {
			t.Errorf("scope: got %q", scope)
		}
		// Verify aud contains the server URL.
		switch aud := claims["aud"].(type) {
		case string:
			if !strings.HasPrefix(aud, serverURL) {
				t.Errorf("aud: got %q, want prefix %q", aud, serverURL)
			}
		case []interface{}:
			found := false
			for _, a := range aud {
				if s, ok := a.(string); ok && strings.HasPrefix(s, serverURL) {
					found = true
				}
			}
			if !found {
				t.Errorf("aud: %v does not contain server URL %q", aud, serverURL)
			}
		default:
			t.Errorf("unexpected aud type %T", claims["aud"])
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"access_token": "test-token",
			"expires_in":   3600,
			"token_type":   "Bearer",
		})
	}))
	defer srv.Close()
	serverURL = srv.URL

	key := &KeyFile{
		Type:         "service_account",
		ProjectID:    "test-project",
		PrivateKeyID: "key-id-001",
		PrivateKey:   pemStr,
		ClientEmail:  "sa@test-project.iam.gserviceaccount.com",
		TokenURI:     srv.URL + "/token",
	}

	tr, err := FetchAccessToken(context.Background(), key, "https://www.googleapis.com/auth/cloud-platform")
	if err != nil {
		t.Fatalf("FetchAccessToken: %v", err)
	}
	if tr.AccessToken != "test-token" {
		t.Errorf("AccessToken: got %q, want %q", tr.AccessToken, "test-token")
	}
	if tr.ExpiresIn != 3600 {
		t.Errorf("ExpiresIn: got %d, want 3600", tr.ExpiresIn)
	}
}

// TestFetchAccessToken_BadPEM verifies that a non-PEM private_key returns a
// descriptive error rather than panicking.
func TestFetchAccessToken_BadPEM(t *testing.T) {
	key := &KeyFile{
		PrivateKeyID: "kid",
		PrivateKey:   "not a PEM",
		ClientEmail:  "sa@proj.iam.gserviceaccount.com",
		TokenURI:     "https://oauth2.googleapis.com/token",
	}
	_, err := FetchAccessToken(context.Background(), key, "some-scope")
	if err == nil {
		t.Fatal("expected error for bad PEM, got nil")
	}
	t.Logf("BadPEM error: %v", err)
}

// TestFetchAccessToken_NonRSAKey verifies that an ECDSA key is rejected with a
// descriptive error mentioning RSA/expected type.
func TestFetchAccessToken_NonRSAKey(t *testing.T) {
	ecKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate EC key: %v", err)
	}
	pkcs8Bytes, err := x509.MarshalPKCS8PrivateKey(ecKey)
	if err != nil {
		t.Fatalf("marshal EC key PKCS8: %v", err)
	}
	pemBlock := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pkcs8Bytes})

	key := &KeyFile{
		PrivateKeyID: "kid",
		PrivateKey:   string(pemBlock),
		ClientEmail:  "sa@proj.iam.gserviceaccount.com",
		TokenURI:     "https://oauth2.googleapis.com/token",
	}
	_, err = FetchAccessToken(context.Background(), key, "some-scope")
	if err == nil {
		t.Fatal("expected error for EC key, got nil")
	}
	errMsg := err.Error()
	if !strings.Contains(errMsg, "RSA") && !strings.Contains(errMsg, "rsa") && !strings.Contains(errMsg, "expected") {
		t.Errorf("error should mention RSA/expected, got: %q", errMsg)
	}
	t.Logf("NonRSAKey error: %v", err)
}

// TestFetchAccessToken_TokenEndpoint401 verifies that a 401 response from the
// token endpoint is surfaced as an error.
func TestFetchAccessToken_TokenEndpoint401(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
	}))
	defer srv.Close()

	_, pemStr := makeRSAKeyPEM(t)
	key := &KeyFile{
		PrivateKeyID: "kid",
		PrivateKey:   pemStr,
		ClientEmail:  "sa@proj.iam.gserviceaccount.com",
		TokenURI:     srv.URL + "/token",
	}
	_, err := FetchAccessToken(context.Background(), key, "some-scope")
	if err == nil {
		t.Fatal("expected error for 401 response, got nil")
	}
	t.Logf("TokenEndpoint401 error: %v", err)
}

// TestFetchAccessToken_PKCS1Fallback verifies that RSA keys encoded in PKCS1
// ("RSA PRIVATE KEY" PEM header) are accepted.  Older Google-issued service
// account keys use this format.
func TestFetchAccessToken_PKCS1Fallback(t *testing.T) {
	privKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate RSA key: %v", err)
	}
	// Marshal PKCS1 — the older Google format.
	pkcs1Bytes := x509.MarshalPKCS1PrivateKey(privKey)
	pemBlock := pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: pkcs1Bytes,
	})

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			t.Errorf("parse form: %v", err)
		}
		rawJWS := r.FormValue("assertion")
		tok, err := josejwt.ParseSigned(rawJWS, []jose.SignatureAlgorithm{jose.RS256})
		if err != nil {
			t.Errorf("parse signed JWT: %v", err)
			http.Error(w, "bad jwt", http.StatusBadRequest)
			return
		}
		var claims map[string]interface{}
		if err := tok.Claims(privKey.Public(), &claims); err != nil {
			t.Errorf("verify JWT signature with PKCS1 key: %v", err)
			http.Error(w, "sig verify failed", http.StatusUnauthorized)
			return
		}

		// Use url.Values to encode the response URL properly for comparison.
		reqURL := r.URL
		_ = reqURL
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"access_token": "pkcs1-token",
			"expires_in":   3600,
			"token_type":   "Bearer",
		})
	}))
	defer srv.Close()

	key := &KeyFile{
		PrivateKeyID: "kid",
		PrivateKey:   string(pemBlock),
		ClientEmail:  "sa@proj.iam.gserviceaccount.com",
		TokenURI:     srv.URL + "/token",
	}
	tr, err := FetchAccessToken(context.Background(), key, "cloud-platform")
	if err != nil {
		t.Fatalf("PKCS1Fallback: %v", err)
	}
	if tr.AccessToken != "pkcs1-token" {
		t.Errorf("AccessToken: got %q, want pkcs1-token", tr.AccessToken)
	}
}

// Ensure url package is used (suppress unused import if needed).
var _ = url.Values{}
