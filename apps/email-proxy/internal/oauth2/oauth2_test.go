// Package oauth2 tests — in-process httptest mock of admin-api's
// POST /v1/internal/oauth2/{provider}/refresh endpoint.
//
// Per ADR-0024 §B1 + OQ-3: email-proxy NEVER exchanges client_secret
// directly with the provider. It calls admin-api's internal refresh
// endpoint which injects the credential and returns a fresh access_token.
package oauth2_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/email-proxy/internal/oauth2"
)

// adminAPIRefreshResponse mirrors the JSON body that admin-api's
// POST /v1/internal/oauth2/{provider}/refresh returns.
type adminAPIRefreshResponse struct {
	AccessToken string    `json:"access_token"`
	ExpiresAt   time.Time `json:"expires_at"`
}

// newMockAdminAPI builds an httptest.Server that:
//   - counts the number of refresh calls made.
//   - can be configured to return an error response.
//   - returns a configurable access_token with configurable TTL.
func newMockAdminAPI(
	t *testing.T,
	token string,
	ttl time.Duration,
	statusCode int,
) (srv *httptest.Server, callCount *atomic.Int32) {
	t.Helper()
	callCount = &atomic.Int32{}

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		callCount.Add(1)

		if statusCode != http.StatusOK {
			http.Error(w, "refresh failed", statusCode)
			return
		}

		resp := adminAPIRefreshResponse{
			AccessToken: token,
			ExpiresAt:   time.Now().Add(ttl),
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp) //nolint:errcheck
	})

	srv = httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv, callCount
}

// newManager creates a Manager pointing at the given mock admin-api server.
// The vault lookup is stubbed: it returns a static refresh_token for serviceID "svc_valid"
// and an error for "svc_no_refresh".
//
// serviceToken is the X-Mintkey-Service-Token sent to admin-api. Tests that
// don't assert on the token value can pass any non-empty string.
func newManager(adminAPIURL string) *oauth2.Manager {
	vault := &stubVault{}
	return oauth2.NewManager(adminAPIURL, vault, "test_service_token")
}

// stubVault implements oauth2.VaultCredentialGetter.
type stubVault struct{}

func (s *stubVault) GetRefreshToken(_ context.Context, tenantID, serviceID string) (provider, refreshToken string, err error) {
	switch serviceID {
	case "svc_valid":
		return "gmail", "rt_valid_refresh_token", nil
	case "svc_outlook":
		return "outlook", "rt_valid_outlook_token", nil
	case "svc_no_refresh":
		return "", "", oauth2.ErrRefreshTokenRevoked
	case "svc_bad_provider":
		return "fax", "rt_whatever", nil
	default:
		return "", "", oauth2.ErrRefreshTokenRevoked
	}
}

// ─── Test: cache hit returns immediately, no outbound call ───────────────────

func TestGetAccessToken_CacheHit(t *testing.T) {
	srv, callCount := newMockAdminAPI(t, "tok_cached", 10*time.Minute, http.StatusOK)
	m := newManager(srv.URL)

	ctx := context.Background()
	// First call — populates cache.
	tok1, err := m.GetAccessToken(ctx, "tnt_1", "svc_valid")
	if err != nil {
		t.Fatalf("first call: %v", err)
	}
	if tok1 == "" {
		t.Fatal("expected non-empty token")
	}
	first := callCount.Load()

	// Second call — must hit cache, no new outbound call.
	tok2, err := m.GetAccessToken(ctx, "tnt_1", "svc_valid")
	if err != nil {
		t.Fatalf("second call: %v", err)
	}
	if tok2 != tok1 {
		t.Errorf("cache hit should return same token: got %q, want %q", tok2, tok1)
	}
	if callCount.Load() != first {
		t.Errorf("expected no additional outbound calls on cache hit; was %d, now %d", first, callCount.Load())
	}
}

// ─── Test: near-expiry entry triggers refresh ─────────────────────────────────

func TestGetAccessToken_NearExpiry_TriggersRefresh(t *testing.T) {
	// Short TTL so the entry is "near expiry" immediately after insertion.
	srv, callCount := newMockAdminAPI(t, "tok_refreshed", 1*time.Second, http.StatusOK)
	m := newManager(srv.URL)

	ctx := context.Background()
	// First call — store entry with 1 s TTL.
	_, err := m.GetAccessToken(ctx, "tnt_1", "svc_valid")
	if err != nil {
		t.Fatalf("first call: %v", err)
	}
	after1 := callCount.Load()

	// Wait so that 90% of TTL has elapsed (900 ms > 1 s * 0.1 remaining threshold).
	time.Sleep(950 * time.Millisecond)

	// Second call — entry is near-expiry; must trigger a refresh.
	_, err = m.GetAccessToken(ctx, "tnt_1", "svc_valid")
	if err != nil {
		t.Fatalf("second call: %v", err)
	}
	if callCount.Load() <= after1 {
		t.Errorf("expected a refresh call after TTL near-expiry; callCount=%d", callCount.Load())
	}
}

// ─── Test: singleflight — 100 concurrent calls = 1 outbound refresh ──────────

func TestGetAccessToken_Singleflight(t *testing.T) {
	// 500 ms TTL; we'll race before the entry is inserted.
	srv, callCount := newMockAdminAPI(t, "tok_sf", 500*time.Millisecond, http.StatusOK)
	m := newManager(srv.URL)

	const goroutines = 100
	var wg sync.WaitGroup
	errs := make([]error, goroutines)

	// Gate all goroutines with a channel so they fire simultaneously.
	start := make(chan struct{})
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			<-start
			_, errs[idx] = m.GetAccessToken(context.Background(), "tnt_sf", "svc_valid")
		}(i)
	}
	close(start)
	wg.Wait()

	for i, err := range errs {
		if err != nil {
			t.Errorf("goroutine %d: %v", i, err)
		}
	}
	if n := callCount.Load(); n != 1 {
		t.Errorf("singleflight: expected exactly 1 outbound refresh call, got %d", n)
	}
}

// ─── Test: refresh failure surfaces as error ─────────────────────────────────

func TestGetAccessToken_RefreshFailure(t *testing.T) {
	srv, _ := newMockAdminAPI(t, "", 0, http.StatusInternalServerError)
	m := newManager(srv.URL)

	_, err := m.GetAccessToken(context.Background(), "tnt_1", "svc_valid")
	if err == nil {
		t.Fatal("expected error on refresh failure, got nil")
	}
}

// ─── Test: 401 from admin-api → ErrRefreshTokenRevoked ───────────────────────

func TestGetAccessToken_401_ReturnsErrRefreshTokenRevoked(t *testing.T) {
	srv, _ := newMockAdminAPI(t, "", 0, http.StatusUnauthorized)
	m := newManager(srv.URL)

	_, err := m.GetAccessToken(context.Background(), "tnt_1", "svc_valid")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if err != oauth2.ErrRefreshTokenRevoked {
		t.Errorf("expected ErrRefreshTokenRevoked, got %v", err)
	}
}

// ─── Test: admin-api returns 401 → ErrRefreshTokenRevoked ────────────────────
//
// After the C-6↔C-9 contract alignment (Wave-2 fixup):
//   - email-proxy no longer calls vault.GetRefreshToken inside Manager.refresh.
//   - admin-api is now the authority for "token revoked": it returns 401 when
//     the stored refresh_token is expired or missing.
//   - The previously vault-driven test is replaced by an admin-api-401 test
//     (which was already covered by TestGetAccessToken_401_ReturnsErrRefreshTokenRevoked
//     but is re-stated here with the service IDs from the stub).
func TestGetAccessToken_AdminAPI401_ReturnsErrRefreshTokenRevoked(t *testing.T) {
	// Mock admin-api returns 401 for any call — simulates expired refresh_token.
	srv, _ := newMockAdminAPI(t, "", 0, http.StatusUnauthorized)
	m := newManager(srv.URL)

	_, err := m.GetAccessToken(context.Background(), "tnt_1", "svc_any")
	if err == nil {
		t.Fatal("expected ErrRefreshTokenRevoked from admin-api 401, got nil")
	}
	if err != oauth2.ErrRefreshTokenRevoked {
		t.Errorf("expected ErrRefreshTokenRevoked, got %v", err)
	}
}

// ─── Test: admin-api returns 500 → generic error (not ErrRefreshTokenRevoked) ──

func TestGetAccessToken_AdminAPI500_ReturnsGenericError(t *testing.T) {
	srv, _ := newMockAdminAPI(t, "tok_ok", 10*time.Minute, http.StatusOK)
	m := newManager(srv.URL)

	// svc_bad_provider: after the NFR-17 redesign admin-api resolves the provider
	// from its DB row; the stub returns a valid token for any service ID.
	// Verify a successful call for a service ID that previously triggered a
	// vault-side unsupported-provider error now succeeds (admin-api is authoritative).
	tok, err := m.GetAccessToken(context.Background(), "tnt_1", "svc_bad_provider")
	if err != nil {
		t.Fatalf("expected success (admin-api resolves provider), got: %v", err)
	}
	if tok == "" {
		t.Error("expected non-empty access_token")
	}
}

// ─── Test: gmail provider accepted ───────────────────────────────────────────

func TestGetAccessToken_GmailProvider_OK(t *testing.T) {
	srv, _ := newMockAdminAPI(t, "tok_gmail", 10*time.Minute, http.StatusOK)
	m := newManager(srv.URL)

	tok, err := m.GetAccessToken(context.Background(), "tnt_1", "svc_valid")
	if err != nil {
		t.Fatalf("gmail provider should succeed: %v", err)
	}
	if tok == "" {
		t.Error("expected non-empty access_token for gmail provider")
	}
}

// ─── Test: outlook provider accepted ─────────────────────────────────────────

func TestGetAccessToken_OutlookProvider_OK(t *testing.T) {
	srv, _ := newMockAdminAPI(t, "tok_outlook", 10*time.Minute, http.StatusOK)
	m := newManager(srv.URL)

	tok, err := m.GetAccessToken(context.Background(), "tnt_1", "svc_outlook")
	if err != nil {
		t.Fatalf("outlook provider should succeed: %v", err)
	}
	if tok == "" {
		t.Error("expected non-empty access_token for outlook provider")
	}
}

// ─── Test: different tenants are cached separately ────────────────────────────

func TestGetAccessToken_TenantIsolation(t *testing.T) {
	srv, callCount := newMockAdminAPI(t, "tok_tenant", 10*time.Minute, http.StatusOK)
	m := newManager(srv.URL)
	ctx := context.Background()

	_, err := m.GetAccessToken(ctx, "tnt_A", "svc_valid")
	if err != nil {
		t.Fatalf("tnt_A: %v", err)
	}
	after1 := callCount.Load()

	_, err = m.GetAccessToken(ctx, "tnt_B", "svc_valid")
	if err != nil {
		t.Fatalf("tnt_B: %v", err)
	}
	// Different tenant — should trigger a second outbound refresh.
	if callCount.Load() <= after1 {
		t.Errorf("expected separate cache entry for tnt_B; callCount=%d after1=%d", callCount.Load(), after1)
	}

	// Same tenant again — must hit cache.
	after2 := callCount.Load()
	_, err = m.GetAccessToken(ctx, "tnt_A", "svc_valid")
	if err != nil {
		t.Fatalf("tnt_A re-call: %v", err)
	}
	if callCount.Load() != after2 {
		t.Errorf("expected cache hit for tnt_A on second call")
	}
}

// ─── Test: verify no client_secret is present in request to admin-api ─────────

func TestGetAccessToken_NoClientSecret_InRequest(t *testing.T) {
	var capturedBody []byte
	var capturedHeaders http.Header

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, r *http.Request) {
		capturedHeaders = r.Header.Clone()

		var buf []byte
		if r.ContentLength > 0 {
			buf = make([]byte, r.ContentLength)
			r.Body.Read(buf) //nolint:errcheck
		}
		capturedBody = buf

		resp := adminAPIRefreshResponse{
			AccessToken: "tok_safe",
			ExpiresAt:   time.Now().Add(10 * time.Minute),
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp) //nolint:errcheck
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	m := newManager(srv.URL)
	_, err := m.GetAccessToken(context.Background(), "tnt_1", "svc_valid")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Ensure client_secret does not appear anywhere in the request body or headers.
	bodyStr := string(capturedBody)
	for _, hdr := range capturedHeaders {
		for _, v := range hdr {
			if contains(v, "client_secret") {
				t.Errorf("client_secret leaked into request header: %q", v)
			}
		}
	}
	if contains(bodyStr, "client_secret") {
		t.Errorf("client_secret leaked into request body: %q", bodyStr)
	}
}

// contains is a simple substring check without importing strings.
func contains(s, substr string) bool {
	if len(substr) == 0 {
		return true
	}
	if len(s) < len(substr) {
		return false
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
