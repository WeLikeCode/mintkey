package server

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/email-proxy/internal/config"
	"github.com/mintkey/mintkey/services/email-proxy/internal/pool"
	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server/handlers"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"

	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
	smtppkg "github.com/mintkey/mintkey/services/email-proxy/internal/smtp"
)

// noopPool is a minimal PoolGetter that always errors (sufficient for routing tests).
type noopPool struct{}

func (n *noopPool) Get(_ context.Context, _ pool.ServiceConfig) (*imapwrap.Client, error) {
	return nil, nil
}
func (n *noopPool) Release(_ pool.ServiceConfig, _ *imapwrap.Client) {}

// noopOAuth2 is a minimal OAuth2Manager for routing tests.
type noopOAuth2 struct{}

func (n *noopOAuth2) GetAccessToken(_ context.Context, _, _ string) (string, error) {
	return "", nil
}

// noopVault is a minimal VaultGetter for routing tests.
type noopVault struct{}

func (n *noopVault) GetCredential(_ context.Context, _, _ string, _ vault.AuthScheme) (*vault.Credential, error) {
	return &vault.Credential{Value: []byte(`{}`)}, nil
}

// noopSMTP is a minimal SMTPSender for routing tests.
type noopSMTP struct{}

func (n *noopSMTP) Send(_ context.Context, _ smtppkg.Credential, _ smtppkg.EmailSendRequest, _ smtppkg.DialTarget) (string, error) {
	return "", nil
}

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
	rl := security.NewRateLimiter()
	emailHdlr := handlers.New(&noopPool{}, &noopOAuth2{}, &noopVault{}, &noopSMTP{}, rl, handlers.NoopAuditEmitter(), nil)
	// Use a nil validator — withJWTAuth tests below create their own.
	return newWithHandlers(cfg, vc, nil, emailHdlr)
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
	s := New(cfg, vc, validator, nil)

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

// TestEmailRoutes_RequireAuth verifies that all /v1/email-proxy/* routes require JWT auth.
// Without a bearer token, each should return 401.
func TestEmailRoutes_RequireAuth(t *testing.T) {
	s := newTestServer(t)
	// Attach a real (but unreachable) validator so withJWTAuth can reject the request.
	cache, _ := auth.NewJWKSCache("http://localhost:9999/.well-known/jwks.json")
	validator := auth.NewValidator(cache)
	s.validator = validator

	routes := []struct {
		method string
		path   string
	}{
		{http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01"},
		{http.MethodGet, "/v1/email-proxy/messages?service_id=svc_01"},
		{http.MethodPost, "/v1/email-proxy/messages?service_id=svc_01"},
		{http.MethodGet, "/v1/email-proxy/messages/search?service_id=svc_01&query=test"},
	}

	for _, tc := range routes {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, nil)
			// No Authorization header.
			rr := httptest.NewRecorder()
			s.routes().ServeHTTP(rr, req)
			if rr.Code != http.StatusUnauthorized {
				t.Errorf("expected 401 (no auth), got %d for %s %s", rr.Code, tc.method, tc.path)
			}
		})
	}
}
