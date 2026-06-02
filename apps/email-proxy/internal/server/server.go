// Package server implements the Email Proxy HTTP server.
//
// C-7 replaces the stub-501 routes with real handler functions from the
// internal/server/handlers package. The 9 endpoints are:
//
//	GET    /v1/email-proxy/mailboxes                            — list_mailboxes
//	GET    /v1/email-proxy/messages                            — list_emails
//	POST   /v1/email-proxy/messages                            — send_email
//	GET    /v1/email-proxy/messages/search                     — search_emails
//	GET    /v1/email-proxy/messages/{id}                       — read_email
//	DELETE /v1/email-proxy/messages/{id}                       — delete_email
//	PATCH  /v1/email-proxy/messages/{id}/flags                 — mark_email
//	POST   /v1/email-proxy/messages/{id}/move                  — move_email
//	GET    /v1/email-proxy/messages/{id}/attachments/{att_id}  — download_attachment
//
// Middleware stack (in order):
//  1. loggingMiddleware — structured request/response log at INFO.
//  2. withJWTAuth — Bearer JWT validation + claims injection into context.
//  3. Per-handler scope check, rate limit, and business logic.
//
// Health endpoints (/healthz, /readyz, /metrics) are not wrapped in JWT auth.
package server

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/email-proxy/internal/config"
	emailmetrics "github.com/mintkey/mintkey/services/email-proxy/internal/metrics"
	"github.com/mintkey/mintkey/services/email-proxy/internal/oauth2"
	"github.com/mintkey/mintkey/services/email-proxy/internal/pool"
	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server/handlers"
	"github.com/mintkey/mintkey/services/email-proxy/internal/smtp"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

// Server is the Email Proxy HTTP server.
type Server struct {
	cfg         *config.Config
	vaultClient *vault.Client
	validator   *auth.Validator
	emailHdlr   *handlers.EmailHandlers
	httpServer  *http.Server
}

// New creates a new Server.
//
// The oauth2Manager is built from cfg.AdminAPIInternalURL and
// cfg.EmailProxyServiceToken; all IMAP/SMTP/security dependencies are
// wired here so that main.go only needs to pass the core trio (cfg, vault,
// validator) plus the audit emitter (C-8 injects the real auditq.Queue).
//
// If ae is nil, a no-op emitter is used (useful for tests).
func New(cfg *config.Config, vaultClient *vault.Client, validator *auth.Validator, ae handlers.AuditEmitter) *Server {
	if ae == nil {
		ae = handlers.NoopAuditEmitter()
	}
	// Build email handler dependencies.
	imapPool := pool.New(nil) // nil → defaults (5 conns, 5-min idle)
	oauth2Mgr := oauth2.NewManager(cfg.AdminAPIInternalURL, vaultClient, cfg.EmailProxyServiceToken)
	smtpCfg := smtp.Config{
		// SMTP transport config is resolved per-credential at send time.
		// Default to STARTTLS on 587; per-service overrides land in a later chunk.
		UseSTARTTLS: true,
		Port:        587,
	}
	smtpClient := smtp.New(smtpCfg)
	rateLimiter := security.NewRateLimiter()

	emailHdlr := handlers.New(
		imapPool,
		oauth2Mgr,
		vaultClient,
		smtpClient,
		rateLimiter,
		ae,
	)

	s := &Server{
		cfg:         cfg,
		vaultClient: vaultClient,
		validator:   validator,
		emailHdlr:   emailHdlr,
	}
	s.httpServer = &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.HTTPPort),
		Handler:      s.routes(),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}
	return s
}

// newWithHandlers creates a Server using pre-built EmailHandlers (for tests).
func newWithHandlers(cfg *config.Config, vaultClient *vault.Client, validator *auth.Validator, emailHdlr *handlers.EmailHandlers) *Server {
	s := &Server{
		cfg:         cfg,
		vaultClient: vaultClient,
		validator:   validator,
		emailHdlr:   emailHdlr,
	}
	s.httpServer = &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.HTTPPort),
		Handler: s.routes(),
	}
	return s
}

// Start starts the HTTP server in a background goroutine.
func (s *Server) Start() error {
	slog.Info("email-proxy HTTP server starting", "addr", s.httpServer.Addr)
	go func() {
		if err := s.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("HTTP server error", "error", err)
		}
	}()
	return nil
}

// Shutdown gracefully stops the HTTP server.
func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpServer.Shutdown(ctx)
}

// routes constructs the request multiplexer.
func (s *Server) routes() http.Handler {
	mux := http.NewServeMux()

	// Health and observability — no auth required.
	mux.HandleFunc("/healthz", s.handleHealthz)
	mux.HandleFunc("/readyz", s.handleReadyz)
	mux.HandleFunc("/metrics", promhttp.Handler().ServeHTTP)

	// Email REST endpoints — all protected by JWT auth + claims injection.
	//
	// Route dispatch strategy:
	// The stdlib mux does not support path parameters or method routing natively.
	// We register specific prefixes and dispatch by method + path suffix inside
	// a single dispatcher. This keeps the routing explicit and auditable.
	mux.HandleFunc("/v1/email-proxy/mailboxes", s.withJWTAuth(s.handleMailboxes))
	mux.HandleFunc("/v1/email-proxy/messages/search", s.withJWTAuth(s.handleMessagesSearch))
	mux.HandleFunc("/v1/email-proxy/messages/", s.withJWTAuth(s.handleMessagesSubpath))
	mux.HandleFunc("/v1/email-proxy/messages", s.withJWTAuth(s.handleMessages))

	return s.loggingMiddleware(mux)
}

// ============================================================================
// Route dispatcher functions
// ============================================================================

// handleMailboxes dispatches GET /v1/email-proxy/mailboxes.
func (s *Server) handleMailboxes(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	s.emailHdlr.HandleListMailboxes(w, r)
}

// handleMessages dispatches GET/POST /v1/email-proxy/messages.
func (s *Server) handleMessages(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		s.emailHdlr.HandleListMessages(w, r)
	case http.MethodPost:
		s.emailHdlr.HandleSendMessage(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleMessagesSearch dispatches GET /v1/email-proxy/messages/search.
func (s *Server) handleMessagesSearch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	s.emailHdlr.HandleSearchMessages(w, r)
}

// handleMessagesSubpath dispatches all /v1/email-proxy/messages/{id}/... routes.
//
// URL shapes handled:
//   - GET    /v1/email-proxy/messages/{id}
//   - DELETE /v1/email-proxy/messages/{id}
//   - PATCH  /v1/email-proxy/messages/{id}/flags
//   - POST   /v1/email-proxy/messages/{id}/move
//   - GET    /v1/email-proxy/messages/{id}/attachments/{att_id}
func (s *Server) handleMessagesSubpath(w http.ResponseWriter, r *http.Request) {
	// Strip the /v1/email-proxy/messages/ prefix.
	const prefix = "/v1/email-proxy/messages/"
	tail := strings.TrimPrefix(r.URL.Path, prefix)
	// tail examples: "42", "42/flags", "42/move", "42/attachments/1"

	parts := strings.SplitN(tail, "/", 3)

	switch {
	case len(parts) == 1:
		// /messages/{id}
		switch r.Method {
		case http.MethodGet:
			s.emailHdlr.HandleReadMessage(w, r)
		case http.MethodDelete:
			s.emailHdlr.HandleDeleteMessage(w, r)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}

	case len(parts) == 2 && parts[1] == "flags":
		// /messages/{id}/flags
		if r.Method != http.MethodPatch {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		s.emailHdlr.HandleUpdateFlags(w, r)

	case len(parts) == 2 && parts[1] == "move":
		// /messages/{id}/move
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		s.emailHdlr.HandleMoveMessage(w, r)

	case len(parts) == 3 && parts[1] == "attachments":
		// /messages/{id}/attachments/{att_id}
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		s.emailHdlr.HandleDownloadAttachment(w, r)

	default:
		http.Error(w, "not found", http.StatusNotFound)
	}
}

// ============================================================================
// Health + probe handlers
// ============================================================================

// handleHealthz is the liveness probe — always 200.
func (s *Server) handleHealthz(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("ok")) //nolint:errcheck
}

// handleReadyz is the readiness probe — checks vault-adapter reachability.
func (s *Server) handleReadyz(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	if err := s.vaultClient.ValidateServiceIdentity(ctx); err != nil {
		slog.Warn("readyz: vault-adapter unreachable", "error", err)
		http.Error(w, "vault-adapter not ready", http.StatusServiceUnavailable)
		return
	}
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("ok")) //nolint:errcheck
}

// ============================================================================
// Middleware
// ============================================================================

// withJWTAuth wraps a handler with Bearer JWT validation AND claims injection.
// Returns 401 if the Authorization header is missing or the token is invalid.
// Claims are attached to the request context via handlers.ClaimsContextKey.
func (s *Server) withJWTAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		tokenStr := bearerToken(r)
		if tokenStr == "" {
			http.Error(w, "missing or malformed Authorization header", http.StatusUnauthorized)
			return
		}

		claims, err := s.validator.ValidateBrokeredJWT(tokenStr)
		if err != nil {
			slog.Debug("JWT validation failed", "error", err, "path", r.URL.Path)
			http.Error(w, "invalid or expired token", http.StatusUnauthorized)
			return
		}

		// Inject validated claims into request context for handler use.
		ctx := context.WithValue(r.Context(), handlers.ClaimsContextKey, claims)
		next(w, r.WithContext(ctx))
	}
}

// loggingMiddleware logs each request at INFO level and records Prometheus
// request metrics (mintkey_email_proxy_requests_total,
// mintkey_email_proxy_request_duration_seconds).
func (s *Server) loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		next.ServeHTTP(rw, r)
		dur := time.Since(start).Seconds()
		endpoint := endpointLabel(r.URL.Path, r.Method)
		scope := scopeLabel(r.URL.Path, r.Method)
		emailmetrics.RecordRequest(endpoint, scope, strconv.Itoa(rw.statusCode), dur)
		slog.Info("http.request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", rw.statusCode,
			"duration_ms", time.Since(start).Milliseconds(),
		)
	})
}

// endpointLabel derives a stable endpoint label from the request path and method.
func endpointLabel(path, method string) string {
	switch {
	case path == "/v1/email-proxy/mailboxes":
		return "list_mailboxes"
	case path == "/v1/email-proxy/messages/search":
		return "search_messages"
	case path == "/v1/email-proxy/messages":
		if method == http.MethodPost {
			return "send_message"
		}
		return "list_messages"
	case strings.HasPrefix(path, "/v1/email-proxy/messages/"):
		tail := strings.TrimPrefix(path, "/v1/email-proxy/messages/")
		parts := strings.SplitN(tail, "/", 3)
		switch {
		case len(parts) == 2 && parts[1] == "flags":
			return "update_flags"
		case len(parts) == 2 && parts[1] == "move":
			return "move_message"
		case len(parts) >= 3 && parts[1] == "attachments":
			return "download_attachment"
		default:
			if method == http.MethodDelete {
				return "delete_message"
			}
			return "read_message"
		}
	case path == "/healthz":
		return "healthz"
	case path == "/readyz":
		return "readyz"
	case path == "/metrics":
		return "metrics"
	default:
		return "unknown"
	}
}

// scopeLabel returns the required OAuth2 scope for an endpoint (used as a metric label).
func scopeLabel(path, method string) string {
	switch {
	case path == "/v1/email-proxy/mailboxes":
		return "read:email"
	case path == "/v1/email-proxy/messages/search":
		return "read:email"
	case path == "/v1/email-proxy/messages":
		if method == http.MethodPost {
			return "send:email"
		}
		return "read:email"
	case strings.HasPrefix(path, "/v1/email-proxy/messages/"):
		tail := strings.TrimPrefix(path, "/v1/email-proxy/messages/")
		parts := strings.SplitN(tail, "/", 3)
		switch {
		case len(parts) == 2 && parts[1] == "flags":
			return "write:email"
		case len(parts) == 2 && parts[1] == "move":
			return "write:email"
		default:
			if method == http.MethodDelete {
				return "delete:email"
			}
			return "read:email"
		}
	default:
		return ""
	}
}

// responseWriter captures the status code for logging.
type responseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.statusCode = code
	rw.ResponseWriter.WriteHeader(code)
}

// bearerToken extracts a Bearer token from the Authorization header.
// Returns "" if missing or malformed.
func bearerToken(r *http.Request) string {
	h := r.Header.Get("Authorization")
	const prefix = "Bearer "
	if len(h) <= len(prefix) || h[:len(prefix)] != prefix {
		return ""
	}
	return h[len(prefix):]
}
