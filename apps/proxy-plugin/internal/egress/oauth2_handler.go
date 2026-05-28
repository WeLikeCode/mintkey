// Package egress implements the egress handler orchestration for the proxy plugin.
//
// This file implements the OAuth2 Password Grant egress handler which orchestrates:
//   1. Parse structured credential from Vault response
//   2. Check TokenCache for a valid cached token
//   3. If cache miss or near-expiry: exchange credentials for a new token
//   4. On exchange failure: graceful degradation (use cached token if not fully expired)
//   5. Cache the new token
//   6. Return the token for injection
//   7. Emit token.exchanged audit event
//
// Design constraints (Requirements 20.1, 20.4, 21.3, 21.4, 21.7):
//   - Use cached token if expiry > 30s in the future (no exchange needed).
//   - On cache miss or near-expiry, perform token exchange.
//   - On exchange failure, use cached token if not fully expired (graceful degradation).
//   - Return 502 only after cached token has fully expired.
//   - Emit token.exchanged audit event after every exchange attempt.
//   - NEVER log credential_fields values or token values (P-1, S-SEC-1).
//
// Source: design.md §Egress Handler Orchestration; Requirements 20.1, 20.4, 21.3, 21.4, 21.7.
package egress

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/url"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
)

// OAuth2HandlerResult holds the outcome of the OAuth2 password grant orchestration.
type OAuth2HandlerResult struct {
	// Token is the bearer token to inject on the upstream request.
	Token string
	// Exchanged indicates whether a token exchange was performed (for audit).
	Exchanged bool
	// ExchangeSuccess indicates whether the exchange succeeded (only meaningful if Exchanged=true).
	ExchangeSuccess bool
	// ExchangeLatencyMS is the exchange duration in milliseconds (only meaningful if Exchanged=true).
	ExchangeLatencyMS int64
	// TokenURLHost is the hostname portion of the token_url (for audit redaction).
	TokenURLHost string
}

// OAuth2HandlerDeps holds the dependencies for the OAuth2 egress handler.
type OAuth2HandlerDeps struct {
	Cache     *cache.TokenCache
	Exchanger *credential.TokenExchanger
}

// HandleOAuth2PasswordGrant orchestrates the OAuth2 password grant flow:
// cache check → exchange if needed → graceful degradation → cache result.
//
// Parameters:
//   - ctx: request context
//   - deps: handler dependencies (cache, exchanger)
//   - tenantID: the tenant owning the service
//   - serviceID: the target service
//   - credPayload: the raw JSON credential payload from the Vault Adapter
//
// Returns OAuth2HandlerResult on success, or an error if the token cannot be obtained.
// The error will be one of:
//   - credential.ErrTokenExchangeFailed (502)
//   - credential.ErrTokenEndpointUnreachable (502)
//   - credential.ErrTokenParseFailed (502)
//   - A JSON parse error for the credential payload
func HandleOAuth2PasswordGrant(
	ctx context.Context,
	deps OAuth2HandlerDeps,
	tenantID, serviceID string,
	credPayload []byte,
) (*OAuth2HandlerResult, error) {
	// Step 1: Parse the structured credential payload.
	var cred credential.OAuth2PasswordGrantCredential
	if err := json.Unmarshal(credPayload, &cred); err != nil {
		return nil, fmt.Errorf("oauth2_password_grant: parse credential payload: %w", err)
	}

	// Extract hostname from token_url for audit (host-only redaction per Req 22.1).
	tokenURLHost := extractHost(cred.TokenURL)

	result := &OAuth2HandlerResult{
		TokenURLHost: tokenURLHost,
	}

	// Step 2: Check cache for a valid token (expiry > 30s).
	if token, ok := deps.Cache.Get(tenantID, serviceID); ok {
		// Cache hit — use cached token, no exchange needed.
		result.Token = token
		result.Exchanged = false
		return result, nil
	}

	// Step 3: Cache miss or near-expiry — perform token exchange.
	exchangeReq := credential.ExchangeRequest{
		TokenURL:            cred.TokenURL,
		CredentialFields:    cred.CredentialFields,
		TokenResponsePath:   cred.TokenResponsePath,
		TokenRequestHeaders: cred.TokenRequestHeaders,
	}

	exchangeStart := time.Now()
	exchangeResult, exchangeErr := deps.Exchanger.Exchange(ctx, exchangeReq)
	exchangeLatency := time.Since(exchangeStart).Milliseconds()

	result.Exchanged = true
	result.ExchangeLatencyMS = exchangeLatency

	if exchangeErr != nil {
		// Exchange failed — attempt graceful degradation.
		result.ExchangeSuccess = false

		// Log the failure without credential values (Req 22.7).
		slog.WarnContext(ctx, "oauth2_password_grant: token exchange failed",
			"tenant_id", tenantID,
			"service_id", serviceID,
			"token_url_host", tokenURLHost,
			"error_type", classifyExchangeError(exchangeErr),
		)

		// Graceful degradation: use cached token if not fully expired.
		// GetForDegradation returns the token even within the 30s buffer,
		// as long as it hasn't fully expired.
		if degradedToken, ok := deps.Cache.GetForDegradation(tenantID, serviceID); ok {
			slog.WarnContext(ctx, "oauth2_password_grant: using degraded cached token",
				"tenant_id", tenantID,
				"service_id", serviceID,
			)
			result.Token = degradedToken
			return result, nil
		}

		// No cached token available — return the exchange error (will become 502).
		return result, exchangeErr
	}

	// Step 4: Exchange succeeded — determine expiry and cache the token.
	result.ExchangeSuccess = true
	result.Token = exchangeResult.Token

	expiresAt := cache.DetermineExpiry(exchangeResult.Token, exchangeResult.RawBody)
	deps.Cache.Put(tenantID, serviceID, exchangeResult.Token, expiresAt)

	return result, nil
}

// extractHost extracts only the hostname from a URL string.
// Returns the host (without port) for audit redaction (Req 22.1).
// Returns "unknown" if the URL cannot be parsed.
func extractHost(rawURL string) string {
	if rawURL == "" {
		return "unknown"
	}
	u, err := url.Parse(rawURL)
	if err != nil {
		return "unknown"
	}
	host := u.Hostname()
	if host == "" {
		return "unknown"
	}
	return host
}

// classifyExchangeError returns a safe error classification string for logging.
// Never includes credential values or response bodies.
func classifyExchangeError(err error) string {
	if err == nil {
		return "none"
	}
	if errors.Is(err, credential.ErrTokenExchangeFailed) {
		return "token_exchange_failed"
	}
	if errors.Is(err, credential.ErrTokenEndpointUnreachable) {
		return "token_endpoint_unreachable"
	}
	if errors.Is(err, credential.ErrTokenParseFailed) {
		return "token_parse_failed"
	}
	return "unknown"
}

// ClassifyError returns the error code string for an exchange error.
// Used by the caller to set the appropriate error response code.
func ClassifyError(err error) string {
	if err == nil {
		return ""
	}
	if errors.Is(err, credential.ErrTokenExchangeFailed) {
		return "token_exchange_failed"
	}
	if errors.Is(err, credential.ErrTokenEndpointUnreachable) {
		return "token_endpoint_unreachable"
	}
	if errors.Is(err, credential.ErrTokenParseFailed) {
		return "token_parse_failed"
	}
	return "token_exchange_failed"
}
