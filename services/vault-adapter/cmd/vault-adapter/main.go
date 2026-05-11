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

	"github.com/mintkey/mintkey/services/vault-adapter/internal/cache"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/changes"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/config"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/kek"
	"github.com/mintkey/mintkey/services/vault-adapter/internal/server"
)

func main() {
	cfg := config.Load()

	key, err := kek.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: fatal: %v\n", err)
		os.Exit(1)
	}
	log.Printf("vault-adapter: KEK loaded (%d bytes), env=%s", len(key), cfg.Env)

	dekCache := cache.New(0) // default 5-min TTL
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
	if err := srv.ListenAndServe(ctx, cfg.GRPCPort); err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: serve error: %v\n", err)
		os.Exit(1)
	}
	log.Println("vault-adapter: shutdown complete")
}
