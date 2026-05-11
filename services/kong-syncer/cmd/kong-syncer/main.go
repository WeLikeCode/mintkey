// Kong-syncer — startup, health endpoint, and changes subscriber stub.
//
// Source: design §9; ADR-0014.1; T-1.0.6.
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/mintkey/mintkey/services/kong-syncer/internal/changes"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/config"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/health"
)

func main() {
	cfg := config.Load()
	log.Printf("kong-syncer: starting (env=%s, port=%d)", cfg.Env, cfg.HTTPPort)

	// Changes subscriber: kong-syncer is a global subscriber (AllTenants).
	// WithTenantScope is required per ADR-0014.1; omitting it panics on Start.
	sub := changes.NewClient(nil, changes.WithTenantScope(changes.AllTenants))

	mux := http.NewServeMux()
	mux.Handle("GET /v1/health", health.Handler())

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.HTTPPort),
		Handler: mux,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Run the changes subscriber in the background.
	go sub.Start(ctx)

	errCh := make(chan error, 1)
	go func() {
		log.Printf("kong-syncer: HTTP listening on :%d", cfg.HTTPPort)
		errCh <- srv.ListenAndServe()
	}()

	select {
	case <-ctx.Done():
		_ = srv.Shutdown(context.Background())
	case err := <-errCh:
		fmt.Fprintf(os.Stderr, "kong-syncer: serve error: %v\n", err)
		os.Exit(1)
	}
	log.Println("kong-syncer: shutdown complete")
}
