// Package main is the entry point for the Mintkey Email Proxy.
//
// The Email Proxy is a REST data-plane service that authenticates agents via
// Mintkey brokered JWTs and proxies email operations (IMAP / SMTP / OAuth2)
// to configured email services. It implements ADR-0024: Email Proxy Support.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/email-proxy/internal/config"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
	"github.com/mintkey/mintkey/packages/go/otelinit"
)

func main() {
	// Load configuration (fail-fast on missing required vars).
	cfg, err := config.Load()
	if err != nil {
		slog.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	// Configure structured logging.
	logLevel := slog.LevelInfo
	if cfg.LogLevel == "debug" {
		logLevel = slog.LevelDebug
	}
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: logLevel,
	})))

	// Initialize OpenTelemetry SDK.
	shutdown, err := otelinit.Init(context.Background(), "mintkey.email-proxy", cfg.OTelEndpoint)
	if err != nil {
		slog.Error("failed to initialize OTel", "error", err)
		os.Exit(1)
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := shutdown(ctx); err != nil {
			slog.Warn("OTel shutdown error", "error", err)
		}
	}()

	// Create vault-adapter gRPC client.
	vaultClient, err := vault.NewClient(cfg.VaultGRPCAddr, cfg.VaultIdentityID, cfg.VaultToken)
	if err != nil {
		slog.Error("failed to create vault client", "error", err)
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

	// Initialize JWKS cache and JWT validator.
	jwksCache, err := auth.NewJWKSCache(cfg.BrokerJWKSURL)
	if err != nil {
		slog.Error("failed to create JWKS cache", "error", err)
		os.Exit(1)
	}
	validator := auth.NewValidator(jwksCache)

	// Create and start the HTTP server.
	srv := server.New(cfg, vaultClient, validator)
	if err := srv.Start(); err != nil {
		slog.Error("failed to start HTTP server", "error", err)
		os.Exit(1)
	}

	slog.Info("email-proxy started",
		"http_port", cfg.HTTPPort,
		"metrics_port", cfg.MetricsPort,
		"vault_grpc_addr", cfg.VaultGRPCAddr,
		"broker_jwks_url", cfg.BrokerJWKSURL,
	)

	// Wait for shutdown signal.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	slog.Info("shutting down email-proxy...")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("HTTP server shutdown error", "error", err)
	}

	slog.Info("email-proxy shutdown complete")
}
