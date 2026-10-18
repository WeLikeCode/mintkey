// Package egress implements the egress handler orchestration for the proxy plugin.
//
// This file implements the OAuth2 Client-Credentials egress handler. It mirrors
// the OAuth2 Password Grant handler (oauth2_handler.go) exactly — same cache →
// singleflight → graceful-degradation → cache flow, same OAuth2HandlerResult /
// token.exchanged audit shape, reusing extractHost, classifyExchangeError, and
// clampExchangeTimeoutSeconds — but parses an OAuth2ClientCredentialsCredential
// and calls ExchangeClientCredentials (form + HTTP Basic) instead of the
// password-grant Exchange. The password-grant path is untouched.
//
// A dedicated deps struct + exchanger interface are used (rather than
// OAuth2HandlerDeps) so the password-grant TokenExchangerIface is left unchanged
// (reuse, do not modify). *credential.TokenExchanger satisfies both interfaces.
//
// Source: design.md §Component 1; oauth2-client-credentials-auth spec.
package egress

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"golang.org/x/sync/singleflight"
)

// ClientCredentialsExchangerIface is the minimal interface satisfied by
// *credential.TokenExchanger for client-credentials exchanges. Declared here
// (accept interfaces, return concretes) so tests can supply counting fakes
// without touching the credential package.
type ClientCredentialsExchangerIface interface {
	ExchangeClientCredentials(ctx context.Context, req credential.ClientCredentialsRequest) (*credential.ExchangeResult, error)
}

// OAuth2ClientCredentialsDeps holds the dependencies for the client-credentials
// egress handler. It is the same shape as OAuth2HandlerDeps; a sibling type is
// used so the password-grant TokenExchangerIface is left unchanged.
type OAuth2ClientCredentialsDeps struct {
	Cache     *cache.TokenCache
	Exchanger ClientCredentialsExchangerIface
	// SF coalesces concurrent cache-miss exchanges per (tenant_id, service_id).
	// If nil, no coalescing is applied (a non-nil SF is expected in production).
	SF *singleflight.Group
}

// HandleOAuth2ClientCredentials orchestrates the OAuth2 client-credentials flow:
// cache check → exchange if needed → graceful degradation → cache result.
//
// Returns OAuth2HandlerResult on success, or a typed error (as HandleOAuth2PasswordGrant).
func HandleOAuth2ClientCredentials(
	ctx context.Context,
	deps OAuth2ClientCredentialsDeps,
	tenantID, serviceID string,
	credPayload []byte,
) (*OAuth2HandlerResult, error) {
	// Step 1: Parse the structured credential payload.
	var cred credential.OAuth2ClientCredentialsCredential
	if err := json.Unmarshal(credPayload, &cred); err != nil {
		return nil, fmt.Errorf("oauth2_client_credentials: parse credential payload: %w", err)
	}

	// Extract hostname from token_url for audit (host-only redaction per Req 22.1).
	tokenURLHost := extractHost(cred.TokenURL)

	result := &OAuth2HandlerResult{
		TokenURLHost: tokenURLHost,
	}

	// Step 2: Check cache for a valid token (expiry > 30s).
	if token, ok := deps.Cache.Get(tenantID, serviceID); ok {
		result.Token = token
		result.Exchanged = false
		return result, nil
	}

	// Step 3: Cache miss or near-expiry — perform token exchange, coalescing
	// concurrent misses for the same (tenant_id, service_id) via singleflight.
	exchangeReq := credential.ClientCredentialsRequest{
		TokenURL:          cred.TokenURL,
		ClientID:          cred.ClientID,
		ClientSecret:      cred.ClientSecret,
		Scope:             cred.Scope,
		Audience:          cred.Audience,
		TokenResponsePath: cred.TokenResponsePath,
		Timeout:           clampExchangeTimeoutSeconds(cred.ExchangeTimeoutSeconds),
	}

	type exchangeOutcome struct {
		result    *credential.ExchangeResult
		latencyMS int64
	}

	sfKey := tenantID + "/" + serviceID

	doExchange := func() (exchangeOutcome, error) {
		start := time.Now()
		res, err := deps.Exchanger.ExchangeClientCredentials(ctx, exchangeReq)
		return exchangeOutcome{result: res, latencyMS: time.Since(start).Milliseconds()}, err
	}

	var outcome exchangeOutcome
	var exchangeErr error

	if deps.SF != nil {
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
		slog.WarnContext(ctx, "oauth2_client_credentials: token exchange failed",
			"tenant_id", tenantID,
			"service_id", serviceID,
			"token_url_host", tokenURLHost,
			"error_type", classifyExchangeError(exchangeErr),
		)

		// Graceful degradation: use cached token if not fully expired.
		if degradedToken, ok := deps.Cache.GetForDegradation(tenantID, serviceID); ok {
			slog.WarnContext(ctx, "oauth2_client_credentials: using degraded cached token",
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
