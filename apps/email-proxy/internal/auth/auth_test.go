package auth

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// generateTestKey generates an Ed25519 keypair and returns (pub, priv).
func generateTestKey(t *testing.T) (ed25519.PublicKey, ed25519.PrivateKey) {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("generate Ed25519 key: %v", err)
	}
	return pub, priv
}

// jwksServer starts an httptest server that serves the given keys as JWKS.
func jwksServer(t *testing.T, keys map[string]ed25519.PublicKey) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		type jwk struct {
			Kid string `json:"kid"`
			Kty string `json:"kty"`
			Crv string `json:"crv"`
			X   string `json:"x"`
		}
		var ks []jwk
		for kid, pub := range keys {
			ks = append(ks, jwk{
				Kid: kid,
				Kty: "OKP",
				Crv: "Ed25519",
				X:   base64.RawURLEncoding.EncodeToString(pub),
			})
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{"keys": ks})
	}))
}

// signToken creates a signed EdDSA JWT with the given claims and kid.
func signToken(t *testing.T, priv ed25519.PrivateKey, kid string, claims jwt.MapClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(&jwt.SigningMethodEd25519{}, claims)
	token.Header["kid"] = kid
	s, err := token.SignedString(priv)
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return s
}

// validClaims returns a minimal set of valid brokered JWT claims.
func validClaims() jwt.MapClaims {
	return jwt.MapClaims{
		"iss":        "mintkey-broker",
		"aud":        "email-proxy",
		"sub":        "agent_01ABC",
		"tenant_id":  "tenant_01XYZ",
		"service_id": "svc_01DEF",
		"exp":        float64(time.Now().Add(1 * time.Hour).Unix()),
		"iat":        float64(time.Now().Unix()),
		"scope":      "send:email read:email",
	}
}

func TestValidateBrokeredJWT_HappyPath(t *testing.T) {
	pub, priv := generateTestKey(t)
	srv := jwksServer(t, map[string]ed25519.PublicKey{"kid-1": pub})
	defer srv.Close()

	cache, err := NewJWKSCache(srv.URL)
	if err != nil {
		t.Fatalf("NewJWKSCache: %v", err)
	}
	validator := NewValidator(cache)

	tokenStr := signToken(t, priv, "kid-1", validClaims())
	claims, err := validator.ValidateBrokeredJWT(tokenStr)
	if err != nil {
		t.Fatalf("ValidateBrokeredJWT: %v", err)
	}

	if claims.Subject != "agent_01ABC" {
		t.Errorf("Subject = %q, want agent_01ABC", claims.Subject)
	}
	if claims.TenantID != "tenant_01XYZ" {
		t.Errorf("TenantID = %q", claims.TenantID)
	}
	if claims.ServiceID != "svc_01DEF" {
		t.Errorf("ServiceID = %q", claims.ServiceID)
	}
	if !claims.Has("send:email") {
		t.Error("expected send:email scope")
	}
	if !claims.Has("read:email") {
		t.Error("expected read:email scope")
	}
}

func TestValidateBrokeredJWT_ExpiredToken(t *testing.T) {
	pub, priv := generateTestKey(t)
	srv := jwksServer(t, map[string]ed25519.PublicKey{"kid-1": pub})
	defer srv.Close()

	cache, _ := NewJWKSCache(srv.URL)
	validator := NewValidator(cache)

	claims := validClaims()
	claims["exp"] = float64(time.Now().Add(-1 * time.Hour).Unix())

	tokenStr := signToken(t, priv, "kid-1", claims)
	_, err := validator.ValidateBrokeredJWT(tokenStr)
	if err == nil {
		t.Error("ValidateBrokeredJWT should reject expired token")
	}
}

func TestValidateBrokeredJWT_UnknownKid_ForceRefresh(t *testing.T) {
	pub1, priv1 := generateTestKey(t)
	pub2, priv2 := generateTestKey(t)

	// Server initially serves only kid-1.
	keys := map[string]ed25519.PublicKey{"kid-1": pub1}
	srv := jwksServer(t, keys)
	defer srv.Close()

	cache, _ := NewJWKSCache(srv.URL)
	validator := NewValidator(cache)

	// Prime the cache with kid-1.
	if _, err := cache.GetKey("kid-1"); err != nil {
		// First fetch — ok if broker is reachable.
		t.Logf("initial GetKey: %v", err)
	}

	// Now add kid-2 to the server.
	keys["kid-2"] = pub2

	// Sign token with kid-2 (not yet in cache).
	tokenStr := signToken(t, priv2, "kid-2", validClaims())

	// Should succeed via force-refresh path.
	claims, err := validator.ValidateBrokeredJWT(tokenStr)
	if err != nil {
		t.Fatalf("ValidateBrokeredJWT with kid-2 (force-refresh path): %v", err)
	}
	if claims.Subject != "agent_01ABC" {
		t.Errorf("Subject = %q", claims.Subject)
	}

	// Ensure kid-1 token still works.
	tokenStr1 := signToken(t, priv1, "kid-1", validClaims())
	if _, err := validator.ValidateBrokeredJWT(tokenStr1); err != nil {
		t.Errorf("kid-1 token should still be valid: %v", err)
	}
}

func TestValidateBrokeredJWT_BadAlgorithm(t *testing.T) {
	cache, _ := NewJWKSCache("http://localhost:9999/jwks.json") // unreachable — not needed
	validator := NewValidator(cache)

	// Create HMAC token (wrong alg).
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, validClaims())
	tokenStr, _ := token.SignedString([]byte("secret"))

	_, err := validator.ValidateBrokeredJWT(tokenStr)
	if err == nil {
		t.Error("ValidateBrokeredJWT should reject non-EdDSA token")
	}
}

func TestValidateBrokeredJWT_MissingRequiredClaim(t *testing.T) {
	pub, priv := generateTestKey(t)
	srv := jwksServer(t, map[string]ed25519.PublicKey{"kid-1": pub})
	defer srv.Close()

	cache, _ := NewJWKSCache(srv.URL)
	validator := NewValidator(cache)

	tests := []struct {
		name        string
		removeClaim string
	}{
		{"missing_iss", "iss"},
		{"missing_sub", "sub"},
		{"missing_tenant_id", "tenant_id"},
		{"missing_service_id", "service_id"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			claims := validClaims()
			delete(claims, tt.removeClaim)
			tokenStr := signToken(t, priv, "kid-1", claims)
			_, err := validator.ValidateBrokeredJWT(tokenStr)
			if err == nil {
				t.Errorf("should fail when %q is missing", tt.removeClaim)
			}
		})
	}
}

func TestValidateBrokeredJWT_EmptyToken(t *testing.T) {
	cache, _ := NewJWKSCache("http://localhost:9999")
	validator := NewValidator(cache)
	_, err := validator.ValidateBrokeredJWT("")
	if err == nil {
		t.Error("should fail on empty token")
	}
}

func TestClaims_Has(t *testing.T) {
	c := &Claims{Scopes: []string{"read:email", "send:email"}}
	if !c.Has("read:email") {
		t.Error("expected read:email")
	}
	if !c.Has("send:email") {
		t.Error("expected send:email")
	}
	if c.Has("write:email") {
		t.Error("should not have write:email")
	}
	if c.Has("delete:email") {
		t.Error("should not have delete:email")
	}
}

func TestValidateBrokeredJWT_TntAlias(t *testing.T) {
	pub, priv := generateTestKey(t)
	srv := jwksServer(t, map[string]ed25519.PublicKey{"kid-1": pub})
	defer srv.Close()

	cache, _ := NewJWKSCache(srv.URL)
	validator := NewValidator(cache)

	claims := validClaims()
	delete(claims, "tenant_id")
	claims["tnt"] = "tenant_via_tnt"

	tokenStr := signToken(t, priv, "kid-1", claims)
	got, err := validator.ValidateBrokeredJWT(tokenStr)
	if err != nil {
		t.Fatalf("ValidateBrokeredJWT: %v", err)
	}
	if got.TenantID != "tenant_via_tnt" {
		t.Errorf("TenantID = %q, want tenant_via_tnt", got.TenantID)
	}
}

// TestForceRefreshThrottle verifies that 100 concurrent unknown-kid validation
// attempts result in at most 2 outbound JWKS fetches (initial + one force-refresh),
// not 100. Without the lastForceRefresh throttle, each unknown-kid would zero
// lastFetch and trigger a fresh HTTP GET — a JWKS-endpoint amplification DoS.
func TestForceRefreshThrottle(t *testing.T) {
	fetchCount := 0

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fetchCount++
		// Serve an empty JWKS — no known kids, so every validation will attempt
		// a force-refresh (unknown kid path in ValidateBrokeredJWT).
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{"keys": []interface{}{}})
	}))
	defer srv.Close()

	cache, err := NewJWKSCache(srv.URL)
	if err != nil {
		t.Fatalf("NewJWKSCache: %v", err)
	}
	validator := NewValidator(cache)

	// Generate a valid-looking token signed with an unknown key (will fail validation,
	// but we only care about how many JWKS fetches happen).
	_, priv := generateTestKey(t)
	tokenStr := signToken(t, priv, "unknown-kid-spray", validClaims())

	// Fire 100 validations with the unknown-kid token.
	for i := 0; i < 100; i++ {
		validator.ValidateBrokeredJWT(tokenStr) //nolint:errcheck // expected to fail — key not in JWKS
	}

	// The JWKS server should have been hit at most 2 times:
	//   1. The initial Refresh() triggered by the first GetKey miss.
	//   2. At most one ForceRefresh() (throttled to 5s; all 100 iterations happen in <1s).
	// We allow up to 2 fetches to be robust against a race on the very first call.
	const maxFetches = 2
	if fetchCount > maxFetches {
		t.Errorf("JWKS endpoint was fetched %d times for 100 unknown-kid requests; want ≤%d (throttle not working)", fetchCount, maxFetches)
	}
}

func TestDecodeBase64URL(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantLen int
		wantErr bool
	}{
		{"valid no padding", "SGVsbG8", 5, false},   // "Hello"
		{"valid 2-char pad", "SGk", 2, false},        // "Hi"
		{"valid 1-char pad suffix", "SGVsbG8h", 6, false}, // "Hello!"
		{"invalid length mod 4==1", "A", 0, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := decodeBase64URL(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("decodeBase64URL(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
				return
			}
			if !tt.wantErr && len(got) != tt.wantLen {
				t.Errorf("decodeBase64URL(%q) len = %d, want %d", tt.input, len(got), tt.wantLen)
			}
		})
	}
}
