// Vault Adapter — KEK loading + gRPC server startup.
//
// Source: design §8; ADR-0003; T-1.0.4.
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/mintkey/mintkey/internal/otelinit"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/cache"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/changes"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/config"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/kek"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/server"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
)

func main() {
	cfg := config.Load()

	// Wire OTel SDK with mandatory redaction filter (ADR-0017.6).
	otlpEndpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if otlpEndpoint == "" {
		otlpEndpoint = "otel-collector:4317"
	}
	otelShutdown, err := otelinit.Init(context.Background(), "mintkey/vault-adapter", otlpEndpoint)
	if err != nil {
		log.Printf("vault-adapter: OTel init warning: %v (continuing without telemetry)", err)
	} else {
		defer func() { _ = otelShutdown(context.Background()) }()
	}

	key, err := kek.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: fatal: %v\n", err)
		os.Exit(1)
	}
	log.Printf("vault-adapter: KEK loaded (%d bytes), env=%s", len(key), cfg.Env)

	dekCache := cache.New(0) // default 5-min TTL

	dbPath := os.Getenv("VAULT_DB_PATH")
	if dbPath == "" {
		dbPath = "/tmp/vault-adapter.db"
	}
	st, err := store.New(dbPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: store: %v\n", err)
		os.Exit(1)
	}

	svc := server.NewVaultService(key, st)
	srv := server.New(key)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Start the credential-rotation subscriber if a Postgres DSN is provided.
	if dsn := os.Getenv("MINTKEY_POSTGRES_DSN"); dsn != "" {
		sub := changes.NewSubscriber(dsn, dekCache)
		go func() {
			if err := sub.Start(ctx); err != nil && ctx.Err() == nil {
				log.Printf("vault-adapter: changes subscriber error: %v", err)
			}
		}()
		log.Printf("vault-adapter: credential rotation subscriber started")
	} else {
		log.Printf("vault-adapter: MINTKEY_POSTGRES_DSN not set; credential rotation subscriber disabled")
	}

	log.Printf("vault-adapter: gRPC listening on :%d", cfg.GRPCPort)
	if err := srv.ListenAndServe(ctx, cfg.GRPCPort, svc); err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: serve error: %v\n", err)
		os.Exit(1)
	}
	log.Println("vault-adapter: shutdown complete")
}
