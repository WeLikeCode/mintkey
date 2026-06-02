// Package server implements the Email Proxy HTTP server.
//
// Phase C-2 exposes:
//   - /healthz  — always 200 OK (liveness).
//   - /readyz   — 200 if vault-adapter is reachable; 503 otherwise.
//   - /metrics  — Prometheus metrics via promhttp.
//
// Stub handlers for /v1/email-proxy/... return 501 Not Implemented.
// Real implementations land in C-7.
//
// Middleware stack (applied to all non-health routes):
//   - JWT auth via internal/auth.Validator.
//   - Structured logging (slog).
//   - OTel trace instrumentation (basic span per request).
package server

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/email-proxy/internal/config"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

// Server is the Email Proxy HTTP server.
type Server struct {
	cfg         *config.Config
	vaultClient *vault.Client
	validator   *auth.Validator
	httpServer  *http.Server
}

// New creates a new Server.
func New(cfg *config.Config, vaultClient *vault.Client, validator *auth.Validator) *Server {
	s := &Server{
		cfg:         cfg,
		vaultClient: vaultClient,
		validator:   validator,
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

	// Stub REST endpoints — require JWT auth (implemented in C-7).
	mux.HandleFunc("/v1/email-proxy/", s.withJWTAuth(s.handleStub))

	return s.loggingMiddleware(mux)
}

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

// handleStub is a placeholder for all /v1/email-proxy/* endpoints.
// Real handlers are implemented in C-7.
func (s *Server) handleStub(w http.ResponseWriter, r *http.Request) {
	http.Error(w, "not implemented — email-proxy REST handlers land in C-7", http.StatusNotImplemented)
}

// withJWTAuth wraps a handler with Bearer JWT validation.
// Returns 401 if the Authorization header is missing or the token is invalid.
// Returns 403 if the token lacks the required scope (checked per-endpoint in C-7).
func (s *Server) withJWTAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		tokenStr := bearerToken(r)
		if tokenStr == "" {
			http.Error(w, "missing or malformed Authorization header", http.StatusUnauthorized)
			return
		}

		_, err := s.validator.ValidateBrokeredJWT(tokenStr)
		if err != nil {
			slog.Debug("JWT validation failed", "error", err, "path", r.URL.Path)
			http.Error(w, "invalid or expired token", http.StatusUnauthorized)
			return
		}

		// C-7: attach claims to request context for handler use.
		next(w, r)
	}
}

// loggingMiddleware logs each request at INFO level.
func (s *Server) loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		next.ServeHTTP(rw, r)
		slog.Info("http.request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", rw.statusCode,
			"duration_ms", time.Since(start).Milliseconds(),
		)
	})
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
