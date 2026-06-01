package auth

import (
	"crypto/ed25519"
	"crypto/rand"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/ssh"
)

func TestDerivePublicKeyFromAPIKey(t *testing.T) {
	apiKey := "mk_agent_test123_random456"

	pubKey1, err := DerivePublicKeyFromAPIKey(apiKey)
	if err != nil {
		t.Fatalf("DerivePublicKeyFromAPIKey() error = %v", err)
	}

	if pubKey1 == nil {
		t.Fatal("DerivePublicKeyFromAPIKey() returned nil")
	}

	// Derive again - should be deterministic
	pubKey2, err := DerivePublicKeyFromAPIKey(apiKey)
	if err != nil {
		t.Fatalf("DerivePublicKeyFromAPIKey() error on second call = %v", err)
	}

	// Keys should be identical
	if string(pubKey1.Marshal()) != string(pubKey2.Marshal()) {
		t.Error("DerivePublicKeyFromAPIKey() not deterministic")
	}

	// Different API key should produce different public key
	pubKey3, err := DerivePublicKeyFromAPIKey("mk_agent_different_random789")
	if err != nil {
		t.Fatalf("DerivePublicKeyFromAPIKey() error on different key = %v", err)
	}

	if string(pubKey1.Marshal()) == string(pubKey3.Marshal()) {
		t.Error("DerivePublicKeyFromAPIKey() produced same key for different API keys")
	}
}

func TestJWKSCache_decodeBase64URL(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantLen int
		wantErr bool
	}{
		{
			name:    "valid base64url - no padding needed",
			input:   "SGVsbG8", // "Hello"
			wantLen: 5,
			wantErr: false,
		},
		{
			name:    "valid base64url - 2 char padding",
			input:   "SGk", // "Hi"
			wantLen: 2,
			wantErr: false,
		},
		{
			name:    "valid base64url - 1 char padding",
			input:   "SGVsbG8h", // "Hello!"
			wantLen: 6,
			wantErr: false,
		},
		{
			name:    "valid base64url with URL-safe chars",
			input:   "PDw_Pz4-", // "<<??>>",
			wantLen: 6,
			wantErr: false,
		},
		{
			name:    "invalid base64url - wrong length",
			input:   "A",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := decodeBase64URL(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("decodeBase64URL() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && len(got) != tt.wantLen {
				t.Errorf("decodeBase64URL() length = %d, want %d", len(got), tt.wantLen)
			}
		})
	}
}

func TestHandler_AuthenticateJWT_InvalidToken(t *testing.T) {
	// This test would require mocking the vault client and JWKS cache
	// For now, we'll just test that invalid tokens are rejected
	// A full integration test would be needed for the complete flow

	// Create a handler with nil dependencies (will fail, but that's expected)
	handler := &Handler{
		cfg:       nil,
		jwksCache: nil,
	}

	// Try to authenticate with invalid JWT
	_, err := handler.AuthenticateJWT("agent_123", []byte("invalid.jwt.token"))
	if err == nil {
		t.Error("AuthenticateJWT() should fail with invalid JWT")
	}
}

func TestHandler_AuthenticatePublicKey_InvalidKey(t *testing.T) {
	// Generate a random Ed25519 key
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	// Convert to SSH public key
	sshPubKey, err := ssh.NewPublicKey(priv.Public())
	if err != nil {
		t.Fatalf("failed to create SSH public key: %v", err)
	}

	// Create a handler with nil dependencies (will fail, but that's expected)
	handler := &Handler{
		cfg:         nil,
		vaultClient: nil,
	}

	// Try to authenticate with unknown key
	_, err = handler.AuthenticatePublicKey("agent_123", sshPubKey)
	if err == nil {
		t.Error("AuthenticatePublicKey() should fail with unknown key")
	}
}

// TestJWTTokenCreation tests creating a valid JWT token (for testing purposes).
func TestJWTTokenCreation(t *testing.T) {
	// Generate Ed25519 key pair
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	// Create JWT token
	token := jwt.NewWithClaims(&jwt.SigningMethodEd25519{}, jwt.MapClaims{
		"sub":        "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
		"tenant_id":  "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
		"service_id": "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
		"exp":        time.Now().Add(1 * time.Hour).Unix(),
		"iat":        time.Now().Unix(),
	})

	token.Header["kid"] = "test-key-id"

	// Sign token
	tokenString, err := token.SignedString(priv)
	if err != nil {
		t.Fatalf("failed to sign token: %v", err)
	}

	if tokenString == "" {
		t.Error("token string is empty")
	}

	// Verify token
	parsedToken, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodEd25519); !ok {
			t.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return pub, nil
	})

	if err != nil {
		t.Fatalf("failed to parse token: %v", err)
	}

	if !parsedToken.Valid {
		t.Error("token is not valid")
	}

	// Extract claims
	claims, ok := parsedToken.Claims.(jwt.MapClaims)
	if !ok {
		t.Fatal("failed to parse claims")
	}

	if claims["sub"] != "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1" {
		t.Errorf("sub = %v, want agent_01HX5J9F8V8H8V0CG3F2Y5J6A1", claims["sub"])
	}

	if claims["tenant_id"] != "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9" {
		t.Errorf("tenant_id = %v, want tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9", claims["tenant_id"])
	}

	if claims["service_id"] != "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1" {
		t.Errorf("service_id = %v, want svc_01HX5J9F8V8H8V0CG3F2Y5J6S1", claims["service_id"])
	}
}

func TestHandler_ValidateAPIKey_InvalidFormat(t *testing.T) {
	handler := &Handler{}

	tests := []struct {
		name   string
		apiKey string
	}{
		{
			name:   "empty string",
			apiKey: "",
		},
		{
			name:   "missing prefix",
			apiKey: "agent_test123_random456",
		},
		{
			name:   "wrong prefix",
			apiKey: "mk_service_test123_random456",
		},
		{
			name:   "too few parts",
			apiKey: "mk_agent",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := handler.ValidateAPIKey(tt.apiKey)
			if err == nil {
				t.Error("ValidateAPIKey() should fail with invalid format")
			}
		})
	}
}
