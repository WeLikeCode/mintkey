// Package jwt provides JWT verification for the Mintkey Egress Proxy plugin.
//
// The verifier validates JWS EdDSA (Ed25519) tokens per ADR-0006.
// It does NOT cache plaintext credentials — per ADR-0014.4 the plugin calls
// the Vault Adapter on every request.
//
// Source: design §10; ADR-0004; ADR-0006; ADR-0014.4; T-1.0.7; T-1.6.1.
package jwt

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"strings"
	"time"
)

// VerifyError is returned by Verify when the token is invalid.
// Code is one of: "invalid_format", "signature_invalid", "expired",
// "token_expired", "unknown_kid", "audience_mismatch", "tenant_mismatch",
// "action_not_granted".
type VerifyError struct {
	Code    string
	Message string
}

func (e *VerifyError) Error() string { return e.Code + ": " + e.Message }

// VerifyOptions contains the expected values to validate JWT claims against.
// Zero values disable the corresponding check (empty string = skip that check).
type VerifyOptions struct {
	ExpectedServiceID string // must match aud[0]
	ExpectedTenantID  string // must match tnt
	ExpectedAction    string // must match scope
	ClockSkewSeconds  int64  // tolerance for exp check; 0 uses default of 30s
}

const defaultClockSkewSeconds int64 = 30

// Verify validates a JWT string against the provided Ed25519 public keys and options.
// Returns the parsed claims on success, or a *VerifyError on failure.
//
// pubKeys is a map of key-ID → public key. The verifier selects the key by the
// "kid" claim in the JWT header (ADR-0016.2). If kid is absent or unknown,
// it returns unknown_kid.
func Verify(tokenStr string, pubKeys map[string]ed25519.PublicKey, opts VerifyOptions) (map[string]any, error) {
	parts := strings.Split(tokenStr, ".")
	if len(parts) != 3 {
		return nil, &VerifyError{Code: "invalid_format", Message: "token must have three dot-separated parts"}
	}

	headerB64, payloadB64, sigB64 := parts[0], parts[1], parts[2]

	// Decode and lightly validate the header.
	headerJSON, err := base64.RawURLEncoding.DecodeString(headerB64)
	if err != nil {
		return nil, &VerifyError{Code: "invalid_format", Message: "header is not valid base64url"}
	}
	var header map[string]any
	if err := json.Unmarshal(headerJSON, &header); err != nil {
		return nil, &VerifyError{Code: "invalid_format", Message: "header is not valid JSON"}
	}

	// Select the public key by kid (ADR-0016.2).
	kidVal, _ := header["kid"].(string)
	if kidVal == "" {
		return nil, &VerifyError{Code: "unknown_kid", Message: "JWT header missing kid"}
	}
	pub, ok := pubKeys[kidVal]
	if !ok {
		return nil, &VerifyError{Code: "unknown_kid", Message: "kid not found in trusted key set: " + kidVal}
	}

	// Decode and validate the payload.
	payloadJSON, err := base64.RawURLEncoding.DecodeString(payloadB64)
	if err != nil {
		return nil, &VerifyError{Code: "invalid_format", Message: "payload is not valid base64url"}
	}
	var claims map[string]any
	if err := json.Unmarshal(payloadJSON, &claims); err != nil {
		return nil, &VerifyError{Code: "invalid_format", Message: "payload is not valid JSON"}
	}

	// Decode the signature.
	sig, err := base64.RawURLEncoding.DecodeString(sigB64)
	if err != nil {
		return nil, &VerifyError{Code: "invalid_format", Message: "signature is not valid base64url"}
	}

	// The signed message is header + "." + payload (the raw base64url strings).
	msg := []byte(headerB64 + "." + payloadB64)

	if !ed25519.Verify(pub, msg, sig) {
		return nil, &VerifyError{Code: "signature_invalid", Message: "signature did not verify against trusted key"}
	}

	// --- Claims checks ---

	// exp: token must not be expired, allowing for clock skew.
	skew := opts.ClockSkewSeconds
	if skew == 0 {
		skew = defaultClockSkewSeconds
	}
	if expVal, ok := claims["exp"]; ok {
		var exp int64
		switch v := expVal.(type) {
		case float64:
			exp = int64(v)
		case int64:
			exp = v
		}
		if time.Now().Unix()-skew > exp {
			return nil, &VerifyError{Code: "token_expired", Message: "token has expired"}
		}
	}

	// iss: must be "mintkey/broker".
	if iss, _ := claims["iss"].(string); iss != "mintkey/broker" {
		return nil, &VerifyError{Code: "signature_invalid", Message: "unexpected iss: " + iss}
	}

	// aud: must contain ExpectedServiceID (when set).
	if opts.ExpectedServiceID != "" {
		if !audContains(claims["aud"], opts.ExpectedServiceID) {
			return nil, &VerifyError{Code: "audience_mismatch", Message: "aud does not contain expected service ID"}
		}
	}

	// tnt: must equal ExpectedTenantID (when set).
	if opts.ExpectedTenantID != "" {
		if tnt, _ := claims["tnt"].(string); tnt != opts.ExpectedTenantID {
			return nil, &VerifyError{Code: "tenant_mismatch", Message: "tnt does not match expected tenant ID"}
		}
	}

	// scope: must equal ExpectedAction (when set).
	if opts.ExpectedAction != "" {
		if scope, _ := claims["scope"].(string); scope != opts.ExpectedAction {
			return nil, &VerifyError{Code: "action_not_granted", Message: "scope does not match expected action"}
		}
	}

	return claims, nil
}

// audContains reports whether the aud claim (string or []interface{}) contains target.
func audContains(aud any, target string) bool {
	switch v := aud.(type) {
	case string:
		return v == target
	case []any:
		for _, item := range v {
			if s, ok := item.(string); ok && s == target {
				return true
			}
		}
	}
	return false
}
