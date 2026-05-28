// Package egress implements the egress handler orchestration for the proxy plugin.
//
// This file implements the OAuth2 Password Grant egress handler which orchestrates:
//  1. Parse structured credential from Vault response
//  2. Check TokenCache for a valid cached token
//  3. If cache miss or near-expiry: exchange credentials for a new token, with
//     per-(tenant,service) singleflight coalescing so concurrent misses for the
//     same key trigger exactly ONE upstream token exchange (Req 20/21 thundering-herd
//     protection).
//  4. On exchange failure: graceful degradation (use cached token if not fully expired)
//  5. Cache the new token
//  6. Return the token for injection
//  7. Emit token.exchanged audit event
//
// Design constraints (Requirements 20.1, 20.4, 21.3, 21.4, 21.7):
//   - Use cached token if expiry > 30s in the future (no exchange needed).
//   - On cache miss or near-expiry, perform token exchange.
//   - On exchange failure, use cached token if not fully expired (graceful degradation).
//   - Return 502 only after cached token has fully expired.
//   - Emit token.exchanged audit event after every exchange attempt.
//   - NEVER log credential_fields values or token values (P-1, S-SEC-1).
//   - Concurrent misses for the same (tenant_id, service_id) are coalesced via
//     singleflight: exactly ONE exchange fires; others wait and share the result.
//     A failed exchange propagates to in-flight waiters for that round only — the
//     next request after the flight completes will retry normally.
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
	"golang.org/x/sync/singleflight"
)

// TokenExchangerIface is the minimal interface satisfied by *credential.TokenExchanger.
// Declaring it here (accept interfaces, return concretes) lets tests supply counting
// fakes without touching the credential package.
type TokenExchangerIface interface {
	Exchange(ctx context.Context, req credential.ExchangeRequest) (*credential.ExchangeResult, error)
}

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
	Exchanger TokenExchangerIface
	// SF is a singleflight.Group for per-(tenant_id, service_id) coalescing of
	// concurrent token-exchange calls on a cache miss. If nil, no coalescing is
	// applied (useful for unit tests that pre-date coalescing, though a non-nil SF
	// is expected in production).
	SF *singleflight.Group
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
	// Coalesce concurrent misses for the same (tenant_id, service_id) via
	// singleflight so exactly ONE upstream exchange fires per key per flight.
	// A failed exchange is shared with in-flight waiters for that round;
	// singleflight forgets the key when the call returns, so the next request
	// after the flight will retry and will NOT see a permanently-poisoned entry.
	exchangeReq := credential.ExchangeRequest{
		TokenURL:            cred.TokenURL,
		CredentialFields:    cred.CredentialFields,
		TokenResponsePath:   cred.TokenResponsePath,
		TokenRequestHeaders: cred.TokenRequestHeaders,
	}

	type exchangeOutcome struct {
		result      *credential.ExchangeResult
		latencyMS   int64
	}

	sfKey := tenantID + "/" + serviceID

	doExchange := func() (exchangeOutcome, error) {
		start := time.Now()
		res, err := deps.Exchanger.Exchange(ctx, exchangeReq)
		return exchangeOutcome{result: res, latencyMS: time.Since(start).Milliseconds()}, err
	}

	var outcome exchangeOutcome
	var exchangeErr error

	if deps.SF != nil {
		// Use singleflight: concurrent misses for this key share one exchange call.
		v, err, _ := deps.SF.Do(sfKey, func() (any, error) {
			o, e := doExchange()
			return o, e
		})
		if err == nil {
			outcome = v.(exchangeOutcome)
		}
		exchangeErr = err
	} else {
		outcome, exchangeErr = doExchange()
	}

	result.Exchanged = true
	result.ExchangeLatencyMS = outcome.latencyMS

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
	result.Token = outcome.result.Token

	expiresAt := cache.DetermineExpiry(outcome.result.Token, outcome.result.RawBody)
	deps.Cache.Put(tenantID, serviceID, outcome.result.Token, expiresAt)

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
