// Package auth handles agent authentication for the SSH Proxy.
package auth

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/config"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/session"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/vault"
	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/ssh"
)

// Handler authenticates agents using JWT or public key methods.
type Handler struct {
	cfg         *config.Config
	vaultClient *vault.Client
	jwksCache   *JWKSCache
}

// NewHandler creates a new authentication handler.
func NewHandler(cfg *config.Config) (*Handler, error) {
	vaultClient, err := vault.NewClient(cfg.VaultAddr, cfg.VaultIdentityID, cfg.VaultToken)
	if err != nil {
		return nil, fmt.Errorf("failed to create vault client: %w", err)
	}

	jwksCache, err := NewJWKSCache(cfg.BrokerAddr)
	if err != nil {
		return nil, fmt.Errorf("failed to create JWKS cache: %w", err)
	}

	return &Handler{
		cfg:         cfg,
		vaultClient: vaultClient,
		jwksCache:   jwksCache,
	}, nil
}

// AuthenticateJWT authenticates an agent using a JWT token (password callback).
func (h *Handler) AuthenticateJWT(user string, password []byte) (*session.SessionContext, error) {
	tokenStr := string(password)

	// Parse and validate JWT
	token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
		// Verify algorithm
		if _, ok := token.Method.(*jwt.SigningMethodEd25519); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}

		// Get key ID from token header
		kid, ok := token.Header["kid"].(string)
		if !ok {
			return nil, errors.New("missing kid in token header")
		}

		// Fetch public key from JWKS
		pubKey, err := h.jwksCache.GetKey(kid)
		if err != nil {
			return nil, fmt.Errorf("failed to get key %s: %w", kid, err)
		}

		return pubKey, nil
	})

	if err != nil {
		return nil, fmt.Errorf("JWT validation failed: %w", err)
	}

	if !token.Valid {
		return nil, errors.New("invalid JWT token")
	}

	// Extract claims
	claims, ok := token.Claims.(jwt.MapClaims)
	if !ok {
		return nil, errors.New("failed to parse claims")
	}

	// Extract required claims
	tenantID, ok := claims["tenant_id"].(string)
	if !ok {
		return nil, errors.New("missing tenant_id claim")
	}

	agentID, ok := claims["sub"].(string)
	if !ok {
		return nil, errors.New("missing sub (agent_id) claim")
	}

	serviceID, ok := claims["service_id"].(string)
	if !ok {
		return nil, errors.New("missing service_id claim")
	}

	// Verify user matches agent_id
	if user != agentID {
		return nil, fmt.Errorf("user %q does not match agent_id %q", user, agentID)
	}

	slog.Info("JWT authentication successful",
		"agent_id", agentID,
		"tenant_id", tenantID,
		"service_id", serviceID,
	)

	return &session.SessionContext{
		TenantID:   tenantID,
		AgentID:    agentID,
		ServiceID:  serviceID,
		AuthMethod: "jwt",
	}, nil
}

// AuthenticatePublicKey authenticates an agent using a public key (public key callback).
// It looks up the agent by SSH public key fingerprint via the vault client.
// If the vault client returns ErrNotImplemented (stub not yet wired), it emits
// an ssh.auth.pubkey.unsupported audit log and rejects the authentication.
func (h *Handler) AuthenticatePublicKey(user string, key ssh.PublicKey) (*session.SessionContext, error) {
	fingerprint := ssh.FingerprintSHA256(key)

	if h.vaultClient == nil {
		slog.Warn("ssh.auth.pubkey.unsupported: vault client not configured",
			"user", user,
			"fingerprint", fingerprint,
		)
		return nil, errors.New("ssh.auth.pubkey.unsupported: vault client not configured")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	agent, err := h.vaultClient.GetAgentByFingerprint(ctx, fingerprint)
	if err != nil {
		if errors.Is(err, vault.ErrNotImplemented) {
			slog.Warn("ssh.auth.pubkey.unsupported: vault GetAgentByFingerprint not yet implemented (C7 wires this); rejecting public key auth",
				"user", user,
				"fingerprint", fingerprint,
			)
			return nil, errors.New("ssh.auth.pubkey.unsupported: public key authentication not available (vault wiring pending)")
		}
		return nil, fmt.Errorf("failed to lookup agent by fingerprint: %w", err)
	}

	// Verify user matches agent_id
	if user != agent.ID {
		return nil, fmt.Errorf("user %q does not match agent_id %q", user, agent.ID)
	}

	// Verify agent is active
	if agent.Status != "active" {
		return nil, fmt.Errorf("agent %s is not active (status: %s)", agent.ID, agent.Status)
	}

	slog.Info("public key authentication successful",
		"agent_id", agent.ID,
		"tenant_id", agent.TenantID,
		"fingerprint", fingerprint,
	)

	return &session.SessionContext{
		TenantID:   agent.TenantID,
		AgentID:    agent.ID,
		ServiceID:  "", // Will be specified later
		AuthMethod: "api_key",
	}, nil
}

