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
	adminAPIURL string
	vault       VaultCredentialGetter
	httpClient  *http.Client

	// cache holds *cacheEntry values keyed by cacheKey(tenantID, serviceID).
	cache sync.Map

	// sfGroup deduplicates concurrent refresh calls for the same key.
	sfGroup singleflight.Group
}

// NewManager creates a Manager that calls adminAPIURL for token refreshes
// and uses the given vault for refresh_token retrieval.
func NewManager(adminAPIURL string, vault VaultCredentialGetter) *Manager {
	return &Manager{
		adminAPIURL: strings.TrimRight(adminAPIURL, "/"),
		vault:       vault,
		httpClient:  &http.Client{Timeout: 15 * time.Second},
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
func (m *Manager) refresh(ctx context.Context, tenantID, serviceID string) (string, error) {
	// 1. Retrieve refresh_token from vault.
	provider, refreshToken, err := m.vault.GetRefreshToken(ctx, tenantID, serviceID)
	if err != nil {
		if errors.Is(err, ErrRefreshTokenRevoked) {
			// TODO(C-8): emit audit event "email.oauth2.expired" via audit emitter.
			slog.Warn("oauth2: refresh_token revoked or missing",
				"tenant_id", tenantID,
				"service_id", serviceID,
			)
			return "", ErrRefreshTokenRevoked
		}
		return "", fmt.Errorf("oauth2: vault.GetRefreshToken(%s/%s): %w", tenantID, serviceID, err)
	}

	// 2. Validate provider.
	if _, ok := supportedProviders[provider]; !ok {
		return "", fmt.Errorf("oauth2: unsupported provider %q (must be gmail or outlook)", provider)
	}

	// 3. Call admin-api's internal refresh endpoint.
	accessToken, expiresAt, err := m.callAdminAPIRefresh(ctx, provider, tenantID, serviceID, refreshToken)
	if err != nil {
		return "", err
	}

	// 4. Store in cache.
	entry := &cacheEntry{
		accessToken: accessToken,
		issuedAt:    time.Now(),
		expiresAt:   expiresAt,
	}
	m.cache.Store(cacheKey(tenantID, serviceID), entry)

	return accessToken, nil
}

// callAdminAPIRefresh calls admin-api's
// POST /v1/internal/oauth2/{provider}/refresh with the service-identity
// Bearer token and the refresh_token in the JSON body.
//
// The client_secret is NOT sent here — admin-api injects it from its own
// credential store (per ADR-0024 §B1 + OQ-3).
func (m *Manager) callAdminAPIRefresh(
	ctx context.Context,
	provider, tenantID, serviceID, refreshToken string,
) (accessToken string, expiresAt time.Time, err error) {
	url := fmt.Sprintf("%s/v1/internal/oauth2/%s/refresh", m.adminAPIURL, provider)

	body := strings.NewReader(fmt.Sprintf(
		`{"tenant_id":%q,"service_id":%q,"refresh_token":%q}`,
		tenantID, serviceID, refreshToken,
	))

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, body)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("oauth2: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	// NOTE: no client_secret header — see ADR-0024 §B1.

	resp, err := m.httpClient.Do(req)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("oauth2: POST %s: %w", url, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		// 401 from admin-api means the refresh_token has been revoked upstream.
		// TODO(C-8): emit audit event "email.oauth2.expired" via audit emitter.
		slog.Warn("oauth2: admin-api returned 401 — refresh_token revoked",
			"provider", provider,
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
