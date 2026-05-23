// Package issuer issues Ed25519-signed JWTs for the Mintkey credential broker.
//
// Claims: iss="mintkey/broker", sub=agent_<ULID>, aud=[svc_<ULID>],
// tnt=tenant_<ULID> (prefixed ULID — NOT slug), scope, jti=jti_<ULID>, iat, exp.
// JWS header carries kid (the active key's ULID).
//
// Sources: ADR-0006, ADR-0008, ADR-0017.11, T-1.5.3.
package issuer

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"

	"github.com/mintkey/mintkey/packages/go/ulid"
	"github.com/mintkey/mintkey/services/broker/internal/keys"
	"time"
)

// TokenRequest is the input for JWT issuance.
type TokenRequest struct {
	AgentID    string
	ServiceID  string
	TenantID   string // MUST be prefixed ULID (tenant_<ULID>), NOT a slug
	Scope      string
	TTLSeconds int
}

// Issuer issues Ed25519-signed JWTs.
type Issuer struct {
	privateKey ed25519.PrivateKey
	activeKID  string
	ring       *keys.KeyRing // retained for future JWKS-aware operations
}

// New creates an Issuer with the given signing key and active kid.
func New(privateKey ed25519.PrivateKey, activeKID string, ring *keys.KeyRing) *Issuer {
	return &Issuer{privateKey: privateKey, activeKID: activeKID, ring: ring}
}

// Issue signs a JWT with the claims from TokenRequest.
// The jti is jti_<ULID> (unique per call).
// The tnt claim is TenantID verbatim — must be a prefixed ULID, not a slug.
func (i *Issuer) Issue(req TokenRequest) (string, error) {
	now := time.Now().Unix()
	exp := now + int64(req.TTLSeconds)
	jti := ulid.New("jti_")

	header := map[string]any{
		"alg": "EdDSA",
		"typ": "JWT",
		"kid": i.activeKID,
	}

	claims := map[string]any{
		"iss":   "mintkey/broker",
		"sub":   req.AgentID,
		"aud":   []string{req.ServiceID},
		"tnt":   req.TenantID, // prefixed ULID — ADR-0017.11, ADR-0008
		"scope": req.Scope,
		"jti":   jti,
		"iat":   now,
		"exp":   exp,
	}

	headerBytes, err := json.Marshal(header)
	if err != nil {
		return "", err
	}
	claimsBytes, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}

	headerB64 := base64.RawURLEncoding.EncodeToString(headerBytes)
	claimsB64 := base64.RawURLEncoding.EncodeToString(claimsBytes)

	signingInput := []byte(headerB64 + "." + claimsB64)
	sig := ed25519.Sign(i.privateKey, signingInput)
	sigB64 := base64.RawURLEncoding.EncodeToString(sig)

	return headerB64 + "." + claimsB64 + "." + sigB64, nil
}
