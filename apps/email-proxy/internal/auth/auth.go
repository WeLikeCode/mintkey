package auth

import (
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// Claims holds the validated claims from a brokered JWT.
// All fields are populated from verified token claims.
type Claims struct {
	Issuer    string
	Audience  []string
	Subject   string   // agent_id
	TenantID  string   // tenant_id or tnt claim
	ServiceID string   // service_id claim
	ExpiresAt time.Time
	IssuedAt  time.Time
	Scopes    []string // read:email | send:email | write:email | delete:email
}

// Has reports whether the claims include the given scope.
func (c *Claims) Has(scope string) bool {
	for _, s := range c.Scopes {
		if s == scope {
			return true
		}
	}
	return false
}

// Validator validates brokered JWTs using a cached JWKS.
type Validator struct {
	cache *JWKSCache
}

// NewValidator creates a new JWT validator backed by the given JWKS cache.
func NewValidator(cache *JWKSCache) *Validator {
	return &Validator{cache: cache}
}

// ValidateBrokeredJWT parses and validates a JWS-Ed25519 brokered token.
// Required claims: iss, aud, sub, tenant_id (or tnt), service_id, exp, iat.
// On unknown kid, the JWKS cache is force-refreshed once per ADR-0016.2.
func (v *Validator) ValidateBrokeredJWT(tokenStr string) (*Claims, error) {
	if tokenStr == "" {
		return nil, errors.New("auth: empty token string")
	}

	token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
		// Enforce EdDSA / Ed25519 algorithm.
		if _, ok := token.Method.(*jwt.SigningMethodEd25519); !ok {
			return nil, fmt.Errorf("auth: unexpected signing method %q — EdDSA required", token.Header["alg"])
		}

		kid, ok := token.Header["kid"].(string)
		if !ok || kid == "" {
			return nil, errors.New("auth: missing kid in token header")
		}

		pubKey, err := v.cache.GetKey(kid)
		if err != nil {
			// ADR-0016.2: unknown kid → force-refresh once, retry.
			if ferr := v.cache.ForceRefresh(); ferr != nil {
				return nil, fmt.Errorf("auth: JWKS force-refresh failed: %w", ferr)
			}
			pubKey, err = v.cache.GetKey(kid)
			if err != nil {
				return nil, fmt.Errorf("auth: key %q not found after force-refresh: %w", kid, err)
			}
		}
		return pubKey, nil
	}, jwt.WithValidMethods([]string{"EdDSA"}))

	if err != nil {
		return nil, fmt.Errorf("auth: JWT validation failed: %w", err)
	}
	if !token.Valid {
		return nil, errors.New("auth: token is not valid")
	}

	raw, ok := token.Claims.(jwt.MapClaims)
	if !ok {
		return nil, errors.New("auth: failed to parse token claims")
	}

	claims, err := extractClaims(raw)
	if err != nil {
		return nil, fmt.Errorf("auth: claim extraction failed: %w", err)
	}
	return claims, nil
}

// extractClaims pulls typed claims from jwt.MapClaims.
// Returns an error if any required claim is missing or has the wrong type.
func extractClaims(raw jwt.MapClaims) (*Claims, error) {
	c := &Claims{}

	var err error

	c.Issuer, err = stringClaim(raw, "iss")
	if err != nil {
		return nil, err
	}

	// aud may be a string or []interface{}
	switch a := raw["aud"].(type) {
	case string:
		c.Audience = []string{a}
	case []interface{}:
		for _, v := range a {
			s, ok := v.(string)
			if !ok {
				return nil, errors.New("auth: aud array contains non-string element")
			}
			c.Audience = append(c.Audience, s)
		}
	default:
		return nil, errors.New("auth: missing or invalid aud claim")
	}

	c.Subject, err = stringClaim(raw, "sub")
	if err != nil {
		return nil, err
	}

	// tenant_id or tnt
	if tid, ok := raw["tenant_id"].(string); ok && tid != "" {
		c.TenantID = tid
	} else if tnt, ok := raw["tnt"].(string); ok && tnt != "" {
		c.TenantID = tnt
	} else {
		return nil, errors.New("auth: missing required claim: tenant_id (or tnt)")
	}

	c.ServiceID, err = stringClaim(raw, "service_id")
	if err != nil {
		return nil, err
	}

	// exp / iat — jwt library already validates exp; we just surface them.
	if exp, ok := raw["exp"].(float64); ok {
		c.ExpiresAt = time.Unix(int64(exp), 0)
	} else {
		return nil, errors.New("auth: missing or invalid exp claim")
	}

	if iat, ok := raw["iat"].(float64); ok {
		c.IssuedAt = time.Unix(int64(iat), 0)
	} else {
		return nil, errors.New("auth: missing or invalid iat claim")
	}

	// Scopes — may be a space-separated string or an array.
	c.Scopes = extractScopes(raw)

	return c, nil
}

// extractScopes retrieves email scope strings from the "scope" or "scp" claim.
func extractScopes(raw jwt.MapClaims) []string {
	for _, key := range []string{"scope", "scp"} {
		switch v := raw[key].(type) {
		case string:
			parts := splitScopes(v)
			return filterEmailScopes(parts)
		case []interface{}:
			var out []string
			for _, s := range v {
				if str, ok := s.(string); ok {
					out = append(out, str)
				}
			}
			return filterEmailScopes(out)
		}
	}
	return nil
}

// filterEmailScopes keeps only email-proxy-relevant scope strings.
func filterEmailScopes(scopes []string) []string {
	var out []string
	for _, s := range scopes {
		switch s {
		case "read:email", "send:email", "write:email", "delete:email":
			out = append(out, s)
		}
	}
	return out
}

// splitScopes splits a space-separated scope string.
func splitScopes(s string) []string {
	if s == "" {
		return nil
	}
	var parts []string
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == ' ' {
			if i > start {
				parts = append(parts, s[start:i])
			}
			start = i + 1
		}
	}
	if start < len(s) {
		parts = append(parts, s[start:])
	}
	return parts
}

// stringClaim extracts a required string claim.
func stringClaim(raw jwt.MapClaims, key string) (string, error) {
	v, ok := raw[key].(string)
	if !ok || v == "" {
		return "", fmt.Errorf("auth: missing or invalid required claim %q", key)
	}
	return v, nil
}
