// Package main is the entry point for the Mintkey SSH Proxy.
//
// The SSH Proxy is a bastion server that authenticates agents via Mintkey
// credentials (JWT or API key) and proxies SSH connections to backend servers.
// It implements ADR-0021: SSH Proxy Support.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/config"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/server"
	"github.com/mintkey/mintkey/packages/go/otelinit"
)

func main() {
	var (
		configPath = flag.String("config", "", "Path to config file (optional)")
		healthOnly = flag.Bool("health", false, "Run health check and exit")
	)
	flag.Parse()

	if *healthOnly {
		if err := runHealthCheck(); err != nil {
			fmt.Fprintf(os.Stderr, "health check failed: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("ok")
		os.Exit(0)
	}

	cfg, err := config.Load(*configPath)
	if err != nil {
		slog.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	// Initialize OTel
	shutdown, err := otelinit.Init(context.Background(), "mintkey.ssh-proxy", cfg.OTelEndpoint)
	if err != nil {
		slog.Error("failed to initialize OTel", "error", err)
		os.Exit(1)
	}
	defer func() {
		if err := shutdown(context.Background()); err != nil {
			slog.Error("failed to shutdown OTel", "error", err)
		}
	}()

	// Create SSH server
	srv, err := server.New(cfg)
	if err != nil {
		slog.Error("failed to create SSH server", "error", err)
		os.Exit(1)
	}

	// Start health/metrics HTTP server
	httpServer := startHTTPServer(cfg.HTTPAddr, srv)

	// Start SSH server
	if err := srv.Start(); err != nil {
		slog.Error("failed to start SSH server", "error", err)
		os.Exit(1)
	}

	slog.Info("SSH Proxy started",
		"ssh_addr", cfg.SSHAddr,
		"http_addr", cfg.HTTPAddr,
	)

	// Wait for shutdown signal
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	slog.Info("shutting down...")

	// Graceful shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("SSH server shutdown error", "error", err)
	}

	if err := httpServer.Shutdown(ctx); err != nil {
		slog.Error("HTTP server shutdown error", "error", err)
	}

	slog.Info("shutdown complete")
}

func startHTTPServer(addr string, srv *server.Server) *http.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", srv.HealthHandler)
	mux.HandleFunc("/metrics", srv.MetricsHandler)

	httpServer := &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	go func() {
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("HTTP server error", "error", err)
		}
	}()

	return httpServer
}

func runHealthCheck() error {
	resp, err := http.Get("http://localhost:8087/healthz")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unhealthy: status %d", resp.StatusCode)
	}
	return nil
}
