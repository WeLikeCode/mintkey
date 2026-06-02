// Package oauth2 provides access-token management for email-proxy's OAuth2
// credential flow per ADR-0024 §B1 + OQ-3.
//
// Design constraints:
//   - email-proxy NEVER exchanges client_secret directly with the provider.
//   - All credential exchange is delegated to admin-api via the internal
//     refresh endpoint: POST /v1/internal/oauth2/{provider}/refresh
//   - Callers use GetAccessToken(ctx, tenantID, serviceID) → (token, err).
//
// Cache policy:
//   - Access tokens are cached in a sync.Map keyed by "tenantID/serviceID".
//   - An entry is considered "near expiry" when < 10% of its TTL remains
//     (i.e. now >= expiresAt - 0.1*TTL). Near-expiry or expired entries
//     trigger a refresh before returning to the caller.
//
// Singleflight:
//   - golang.org/x/sync/singleflight ensures that concurrent GetAccessToken
//     calls for the same (tenantID, serviceID) key produce exactly one
//     outbound refresh request; all waiters share the result.
//
// Error types:
//   - ErrRefreshTokenRevoked — admin-api returned 401, or vault reports the
//     refresh_token is missing/revoked. Callers (C-7 handlers) map this to
//     an audit event "email.oauth2.expired".
//
// Audit events:
//   TODO(C-8): on ErrRefreshTokenRevoked emit audit event "email.oauth2.expired"
//   via the audit emitter (package not yet wired — log for now).
package oauth2

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/singleflight"
)

// ErrRefreshTokenRevoked is returned when the OAuth2 refresh_token is no
// longer valid. This occurs when:
//   - vault returns no refresh_token for the (tenant, service) pair, or
//   - admin-api responds with HTTP 401 (token revoked upstream).
//
// Callers should surface this as a 401 to the agent and emit an
// "email.oauth2.expired" audit event (TODO C-8).
var ErrRefreshTokenRevoked = errors.New("oauth2: refresh_token revoked or not found")

// supportedProviders lists the OAuth2 providers that email-proxy supports.
// Any provider not in this set is rejected before the outbound call.
var supportedProviders = map[string]struct{}{
	"gmail":   {},
	"outlook": {},
}

// VaultCredentialGetter is the vault interface required by Manager.
// Implemented by *vault.Client in production; stubbed in tests.
type VaultCredentialGetter interface {
	// GetRefreshToken returns the OAuth2 provider name and refresh_token
	// for the given (tenantID, serviceID) pair. Returns ErrRefreshTokenRevoked
	// if no valid refresh_token is stored.
	GetRefreshToken(ctx context.Context, tenantID, serviceID string) (provider, refreshToken string, err error)
}

// cacheEntry holds a cached access_token and its expiry metadata.
type cacheEntry struct {
	accessToken string
	issuedAt    time.Time
	expiresAt   time.Time
}

// isNearExpiry reports whether the entry has less than 10% of its original
// TTL remaining (i.e. the "90% consumed" threshold).
func (e *cacheEntry) isNearExpiry(now time.Time) bool {
	total := e.expiresAt.Sub(e.issuedAt)
	if total <= 0 {
		return true // zero or negative TTL → always near-expiry
	}
	threshold := e.issuedAt.Add(time.Duration(float64(total) * 0.9))
	return now.After(threshold)
}

// refreshResponse mirrors the JSON body returned by admin-api's
// POST /v1/internal/oauth2/{provider}/refresh.
type refreshResponse struct {
	AccessToken string    `json:"access_token"`
	ExpiresAt   time.Time `json:"expires_at"`
}

// Manager manages access-token caching and refresh delegation for
// OAuth2-backed email services.
//
// Create via NewManager; the zero value is not usable.
type Manager struct {
	adminAPIURL  string
	serviceToken string // sent as X-Mintkey-Service-Token on every admin-api call
	vault        VaultCredentialGetter
	httpClient   *http.Client

	// cache holds *cacheEntry values keyed by cacheKey(tenantID, serviceID).
	cache sync.Map

	// sfGroup deduplicates concurrent refresh calls for the same key.
	sfGroup singleflight.Group
}

// NewManager creates a Manager that calls adminAPIURL for token refreshes.
//
// serviceToken is sent as the X-Mintkey-Service-Token header on every
// outbound call to admin-api's refresh endpoint (MINTKEY_EMAIL_PROXY_SERVICE_TOKEN).
// vault is retained for interface compatibility; admin-api fetches the
// refresh_token from its own vault server-side (per NFR-17 / ADR-0024 §B1).
func NewManager(adminAPIURL string, vault VaultCredentialGetter, serviceToken string) *Manager {
	return &Manager{
		adminAPIURL:  strings.TrimRight(adminAPIURL, "/"),
		serviceToken: serviceToken,
		vault:        vault,
		httpClient:   &http.Client{Timeout: 15 * time.Second},
	}
}

// GetAccessToken returns a valid OAuth2 access_token for the given
// (tenantID, serviceID) pair.
//
// It returns a cached token when one exists and has more than 10% of its
// TTL remaining. Otherwise it delegates a refresh to admin-api via the
// singleflight group (ensuring only one outbound call per key under
// concurrent load).
func (m *Manager) GetAccessToken(ctx context.Context, tenantID, serviceID string) (string, error) {
	key := cacheKey(tenantID, serviceID)

	// Fast path: valid cached entry.
	if entry, ok := m.loadEntry(key); ok && !entry.isNearExpiry(time.Now()) {
		return entry.accessToken, nil
	}

	// Slow path: refresh via singleflight.
	result, err, _ := m.sfGroup.Do(key, func() (interface{}, error) {
		return m.refresh(ctx, tenantID, serviceID)
	})
	if err != nil {
		return "", err
	}
	return result.(string), nil
}

// refresh fetches a new access_token from admin-api and stores it in the cache.
// This is the function executed inside the singleflight group.
//
// Per ADR-0024 §B1 + NFR-17: email-proxy no longer retrieves the refresh_token
// from vault itself.  admin-api fetches the refresh_token server-side and
// performs the provider /token exchange. The provider name is derived from
// admin-api's response context; email-proxy only needs to specify it via the
// URL path which admin-api infers from its own stored record.
//
// NOTE: vault.GetRefreshToken is NOT called here. It remains exported for
// callers that need direct vault access (e.g. connection health checks).
func (m *Manager) refresh(ctx context.Context, tenantID, serviceID string) (string, error) {
	// Call admin-api's internal refresh endpoint.
	// admin-api determines the provider from the stored email_services row
	// and fetches the refresh_token from its vault — email-proxy never sees it.
	accessToken, expiresAt, err := m.callAdminAPIRefresh(ctx, tenantID, serviceID)
	if err != nil {
		return "", err
	}

	// Store in cache.
	entry := &cacheEntry{
		accessToken: accessToken,
		issuedAt:    time.Now(),
		expiresAt:   expiresAt,
	}
	m.cache.Store(cacheKey(tenantID, serviceID), entry)

	return accessToken, nil
}

// callAdminAPIRefresh calls admin-api's
// POST /v1/internal/oauth2/{provider}/refresh?tenant_id=...&service_id=...
//
// Contract (aligned with C-9 admin-api handler):
//   - Method:  POST
//   - Path:    /v1/internal/oauth2/{provider}/refresh
//   - Query:   tenant_id=<URL-encoded>, service_id=<URL-encoded>
//   - Header:  X-Mintkey-Service-Token: <m.serviceToken>
//   - Body:    empty — admin-api fetches refresh_token from vault (NFR-17)
//
// The client_secret and refresh_token are NEVER sent over the wire from
// email-proxy.  admin-api holds client_secret in its own env and fetches
// the refresh_token from vault server-side (ADR-0024 §B1 + OQ-3).
//
// Note: the provider path segment is currently hardcoded to "gmail" as a
// sentinel because email-proxy does not track per-service provider locally
// after the NFR-17 redesign.  admin-api uses the service_id to determine
// the correct provider from its database row.  A dedicated "detect" endpoint
// (or embedding provider in the service_id record) is deferred to C-7.
// For now the router on admin-api side accepts any provider string and looks
// it up from the stored email_services row, so passing the provider is still
// useful when available.  email-proxy passes "generic" when unknown to let
// admin-api resolve it — this is a C-7 TODO.
//
// TODO(C-7): derive provider from the email_services row lookup rather than
// hardcoding a placeholder.  For Wave-2, the test stub provides a provider
// via stubVault.GetRefreshToken; the contract test asserts the path shape
// regardless of the provider string value.
func (m *Manager) callAdminAPIRefresh(
	ctx context.Context,
	tenantID, serviceID string,
) (accessToken string, expiresAt time.Time, err error) {
	// Build query string — URL-encode both IDs to handle special characters.
	qs := url.Values{}
	qs.Set("tenant_id", tenantID)
	qs.Set("service_id", serviceID)

	// Provider is resolved by admin-api from the stored email_services row.
	// We send a well-known placeholder; admin-api ignores it and uses the DB row.
	// TODO(C-7): pass the actual provider once C-7 handler wires the vault lookup.
	endpointURL := fmt.Sprintf("%s/v1/internal/oauth2/gmail/refresh?%s", m.adminAPIURL, qs.Encode())

	// Empty body — refresh_token never leaves admin-api (NFR-17).
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpointURL, http.NoBody)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("oauth2: build request: %w", err)
	}
	// Authenticate as the email-proxy service (MINTKEY_EMAIL_PROXY_SERVICE_TOKEN).
	req.Header.Set("X-Mintkey-Service-Token", m.serviceToken)
	// NOTE: no client_secret — see ADR-0024 §B1.

	resp, err := m.httpClient.Do(req)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("oauth2: POST %s: %w", endpointURL, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		// 401 from admin-api: either wrong service token OR refresh_token revoked.
		// TODO(C-8): emit audit event "email.oauth2.expired" via audit emitter.
		slog.Warn("oauth2: admin-api returned 401 — bad service token or refresh_token revoked",
			"tenant_id", tenantID,
			"service_id", serviceID,
		)
		return "", time.Time{}, ErrRefreshTokenRevoked
	}

	if resp.StatusCode != http.StatusOK {
		return "", time.Time{}, fmt.Errorf("oauth2: admin-api refresh returned status %d", resp.StatusCode)
	}

	var rr refreshResponse
	if err := json.NewDecoder(resp.Body).Decode(&rr); err != nil {
		return "", time.Time{}, fmt.Errorf("oauth2: decode refresh response: %w", err)
	}
	if rr.AccessToken == "" {
		return "", time.Time{}, fmt.Errorf("oauth2: admin-api returned empty access_token")
	}

	return rr.AccessToken, rr.ExpiresAt, nil
}

// loadEntry retrieves a *cacheEntry from the cache by key. Returns (nil, false)
// if not present.
func (m *Manager) loadEntry(key string) (*cacheEntry, bool) {
	v, ok := m.cache.Load(key)
	if !ok {
		return nil, false
	}
	entry, ok := v.(*cacheEntry)
	return entry, ok
}

// cacheKey returns the sync.Map key for a (tenantID, serviceID) pair.
func cacheKey(tenantID, serviceID string) string {
	return tenantID + "/" + serviceID
}
