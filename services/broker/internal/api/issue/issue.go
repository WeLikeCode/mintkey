// Package issue implements POST /v1/issue — the internal Broker endpoint
// used by the MCP Server to obtain a short-lived Ed25519 JWT for an agent.
//
// Design constraints (ADR-0006; ADR-0008; ADR-0017.11; T-1.6.x):
//   - Authenticated by X-Mintkey-Service-Token; all others → 401.
//   - Constant-time compare for token auth.
//   - ttl_seconds must be 1–3600; defaults to 600 when 0.
//   - Response: {token, expires_at} where expires_at is Unix timestamp int64.
//   - Error shape: {"mintkey:code": "...", "title": "..."} — same as resolve.go.
package issue

import (
	"crypto/subtle"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/mintkey/mintkey/services/broker/internal/issuer"
)

// issueRequest is the JSON body expected by the endpoint.
type issueRequest struct {
	AgentID    string `json:"agent_id"`
	ServiceID  string `json:"service_id"`
	TenantID   string `json:"tenant_id"`
	Scope      string `json:"scope"`
	TTLSeconds int    `json:"ttl_seconds"`
}

// issueResponse is the 200 JSON body.
type issueResponse struct {
	Token     string `json:"token"`
	ExpiresAt int64  `json:"expires_at"`
}

// errBody is the JSON error envelope — mirrors the REST API's mintkey:code pattern.
type errBody struct {
	Code  string `json:"mintkey:code"`
	Title string `json:"title"`
}

// Handler holds the dependencies for the issue endpoint.
type Handler struct {
	iss      *issuer.Issuer
	mcpToken string
}

// NewHandler constructs an issue.Handler.
// mcpToken is the shared secret the MCP Server must supply in
// X-Mintkey-Service-Token to authenticate its requests.
func NewHandler(iss *issuer.Issuer, mcpToken string) http.Handler {
	return &Handler{iss: iss, mcpToken: mcpToken}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// 1. Authenticate — service-to-service token.
	if subtle.ConstantTimeCompare(
		[]byte(r.Header.Get("X-Mintkey-Service-Token")),
		[]byte(h.mcpToken),
	) != 1 {
		writeErr(w, http.StatusUnauthorized, "unauthenticated", "Service token missing or invalid")
		return
	}

	// 2. Parse body.
	var req issueRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "validation_failed", "Invalid request body")
		return
	}

	// 3. Validate and apply defaults for ttl_seconds.
	ttl := req.TTLSeconds
	if ttl == 0 {
		ttl = 600
	}
	if ttl < 0 || ttl > 3600 {
		writeErr(w, http.StatusBadRequest, "validation_failed", "ttl_seconds must be between 1 and 3600")
		return
	}

	// 4. Issue the JWT.
	token, err := h.iss.Issue(issuer.TokenRequest{
		AgentID:    req.AgentID,
		ServiceID:  req.ServiceID,
		TenantID:   req.TenantID,
		Scope:      req.Scope,
		TTLSeconds: ttl,
	})
	if err != nil {
		slog.Error("issue: JWT signing error", "err", err)
		writeErr(w, http.StatusInternalServerError, "issuer_error", "Failed to issue token")
		return
	}

	expiresAt := time.Now().Unix() + int64(ttl)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(issueResponse{Token: token, ExpiresAt: expiresAt})
}

func writeErr(w http.ResponseWriter, status int, code, title string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(errBody{Code: code, Title: title})
}
