// Package main is the entry point for the Mintkey Email Proxy.
//
// The Email Proxy is a REST data-plane service that authenticates agents via
// Mintkey brokered JWTs and proxies email operations (IMAP / SMTP / OAuth2)
// to configured email services. It implements ADR-0024: Email Proxy Support.
//
// Boot sequence:
//  1. Load config from environment.
//  2. Configure structured logging.
//  3. Initialize OTel SDK (non-fatal if collector is unreachable).
//  4. Create auditq.Queue (WAL-backed, drains to admin-api).
//  5. Replay any undelivered WAL events from previous run.
//  6. Start audit drainer background worker.
//  7. Create vault-adapter gRPC client + validate identity.
//  8. Initialize JWKS cache + JWT validator.
//  9. Create HTTP server with real AuditEmitter wired in.
// 10. Start HTTP server.
// 11. Block on SIGINT / SIGTERM.
// 12. Graceful shutdown: drain HTTP → drain auditq → flush OTel.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/packages/go/otelinit"
	"github.com/mintkey/mintkey/services/email-proxy/internal/audit"
	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/email-proxy/internal/config"
	_ "github.com/mintkey/mintkey/services/email-proxy/internal/metrics" // registers Prometheus counters via promauto init
	"github.com/mintkey/mintkey/services/email-proxy/internal/server"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

func main() {
	// 1. Load configuration (fail-fast on missing required vars).
	cfg, err := config.Load()
	if err != nil {
		slog.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	// 2. Configure structured logging.
	logLevel := slog.LevelInfo
	if cfg.LogLevel == "debug" {
		logLevel = slog.LevelDebug
	}
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: logLevel,
	})))

	// 3. Initialize OpenTelemetry SDK.
	otelShutdown, err := otelinit.Init(context.Background(), "mintkey.email-proxy", cfg.OTelEndpoint)
	if err != nil {
		slog.Error("failed to initialize OTel", "error", err)
		os.Exit(1)
	}

	// 4. Create auditq.Queue (WAL-backed, drains to admin-api).
	auditQueue := auditq.New(
		cfg.AdminAPIInternalURL,
		cfg.EmailProxyServiceToken,
		cfg.AuditWALPath,
	)

	// 5. Replay undelivered WAL events from previous run.
	auditQueue.Replay()

	// 6. Start audit drainer background worker.
	auditQueue.Start()

	// 7. Create vault-adapter gRPC client.
	vaultClient, err := vault.NewClient(cfg.VaultGRPCAddr, cfg.VaultIdentityID, cfg.VaultToken)
	if err != nil {
		slog.Error("failed to create vault client", "error", err)
		auditQueue.Close()
		os.Exit(1)
	}
	defer vaultClient.Close()

	// Validate service identity at startup (non-fatal: vault-adapter may not be
	// ready in docker compose yet; the readyz probe tracks ongoing health).
	validateCtx, validateCancel := context.WithTimeout(context.Background(), 5*time.Second)
	if err := vaultClient.ValidateServiceIdentity(validateCtx); err != nil {
		slog.Warn("startup vault identity validation failed (proceeding — readyz will reflect status)",
			"error", err)
	}
	validateCancel()

	// 8. Initialize JWKS cache and JWT validator.
	jwksCache, err := auth.NewJWKSCache(cfg.BrokerJWKSURL)
	if err != nil {
		slog.Error("failed to create JWKS cache", "error", err)
		auditQueue.Close()
		os.Exit(1)
	}
	validator := auth.NewValidator(jwksCache)

	// 9. Build the real AuditEmitter backed by the auditq.Queue.
	auditEmitter := audit.NewEmitter(auditQueue)

	// 10. Create and start the HTTP server with the real audit emitter.
	srv := server.New(cfg, vaultClient, validator, auditEmitter)
	if err := srv.Start(); err != nil {
		slog.Error("failed to start HTTP server", "error", err)
		auditQueue.Close()
		os.Exit(1)
	}

	slog.Info("email-proxy started",
		"http_port", cfg.HTTPPort,
		"metrics_port", cfg.MetricsPort,
		"vault_grpc_addr", cfg.VaultGRPCAddr,
		"broker_jwks_url", cfg.BrokerJWKSURL,
		"audit_wal_path", cfg.AuditWALPath,
	)

	// 11. Wait for shutdown signal.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	slog.Info("shutting down email-proxy...")

	// 12. Graceful shutdown in order: HTTP → auditq drain → OTel flush.
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("HTTP server shutdown error", "error", err)
	}

	// Drain the auditq with the remaining budget from the 30 s context.
	auditQueue.CloseWithContext(ctx)

	// Flush OTel (5 s budget — nested inside the 30 s ctx but uses a sub-deadline
	// so shutdown doesn't fully block on a slow collector).
	otelCtx, otelCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer otelCancel()
	if err := otelShutdown(otelCtx); err != nil {
		slog.Warn("OTel shutdown error", "error", err)
	}

	slog.Info("email-proxy shutdown complete")
}
