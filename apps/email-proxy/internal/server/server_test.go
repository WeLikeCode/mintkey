package server

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/email-proxy/internal/config"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

// newTestServer creates a Server with a no-op vault client and a nil validator
// (sufficient for testing healthz and the middleware directly).
func newTestServer(t *testing.T) *Server {
	t.Helper()
	cfg := &config.Config{
		HTTPPort:        8088,
		MetricsPort:     8090,
		VaultIdentityID: "test_id",
		VaultToken:      "test_tok",
		VaultGRPCAddr:   "localhost:9999", // unreachable; readyz will fail
	}
	vc, err := vault.NewClient("localhost:9999", "id", "tok")
	if err != nil {
		t.Fatalf("vault.NewClient: %v", err)
	}
	// Use a nil validator — withJWTAuth tests below create their own.
	return New(cfg, vc, nil)
}

func TestHandleHealthz_Always200(t *testing.T) {
	s := newTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rr := httptest.NewRecorder()
	s.handleHealthz(rr, req)
	if rr.Code != http.StatusOK {
		t.Errorf("healthz status = %d, want 200", rr.Code)
	}
	if rr.Body.String() != "ok" {
		t.Errorf("healthz body = %q, want ok", rr.Body.String())
	}
}

func TestHandleReadyz_VaultUnreachable(t *testing.T) {
	s := newTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	rr := httptest.NewRecorder()
	s.handleReadyz(rr, req)
	// Vault is unreachable (localhost:9999) so readyz returns 503.
	if rr.Code != http.StatusServiceUnavailable {
		t.Errorf("readyz status = %d, want 503 (vault unreachable)", rr.Code)
	}
}

func TestBearerToken_HappyPath(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer my.test.token")
	tok := bearerToken(req)
	if tok != "my.test.token" {
		t.Errorf("bearerToken = %q, want my.test.token", tok)
	}
}

func TestBearerToken_Missing(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	if tok := bearerToken(req); tok != "" {
		t.Errorf("bearerToken = %q, want empty", tok)
	}
}

func TestBearerToken_WrongScheme(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Basic dXNlcjpwYXNz")
	if tok := bearerToken(req); tok != "" {
		t.Errorf("bearerToken = %q, want empty for Basic scheme", tok)
	}
}

func TestWithJWTAuth_MissingToken(t *testing.T) {
	s := newTestServer(t)
	// Supply a nil validator; withJWTAuth must reject before reaching it.
	handler := s.withJWTAuth(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK) // should not be reached
	})

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes", nil)
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401 (no token)", rr.Code)
	}
}

func TestWithJWTAuth_InvalidToken(t *testing.T) {
	// Create a real validator backed by an unreachable JWKS URL so that
	// validation fails (unknown key) rather than panic.
	cache, _ := auth.NewJWKSCache("http://localhost:9999/.well-known/jwks.json")
	validator := auth.NewValidator(cache)

	cfg := &config.Config{HTTPPort: 8088, VaultGRPCAddr: "localhost:9999"}
	vc, _ := vault.NewClient("localhost:9999", "id", "tok")
	s := New(cfg, vc, validator)

	handler := s.withJWTAuth(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK) // should not be reached
	})

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes", nil)
	req.Header.Set("Authorization", "Bearer totally.invalid.token")
	rr := httptest.NewRecorder()
	handler(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401 (invalid token)", rr.Code)
	}
}

func TestHandleStub_Returns501(t *testing.T) {
	s := newTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/anything", nil)
	rr := httptest.NewRecorder()
	s.handleStub(rr, req)
	if rr.Code != http.StatusNotImplemented {
		t.Errorf("stub status = %d, want 501", rr.Code)
	}
}
