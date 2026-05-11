// Credential Broker — Ed25519 key loading + JWKS endpoint + API-key resolve.
//
// Source: design §7; ADR-0006; ADR-0018; T-1.0.5; long-lived-api-keys task 4.1.
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/mintkey/mintkey/services/broker/internal/api/resolve"
	"github.com/mintkey/mintkey/services/broker/internal/config"
	"github.com/mintkey/mintkey/services/broker/internal/keys"
)

func main() {
	cfg := config.Load()

	// Key ring: in the skeleton, load from env or fail.
	// In T-1.0.8+ the private key is fetched from Vault Adapter using svcid_broker.
	ring := keys.NewKeyRing()
	log.Printf("broker: starting (env=%s, port=%d)", cfg.Env, cfg.HTTPPort)

	// DB pool for api-key resolution (nil-safe: resolve handler handles nil store gracefully
	// if DATABASE_URL is not set, but will fail at runtime on actual resolve requests).
	var resolveStore resolve.Store
	if cfg.DatabaseURL != "" {
		pool, err := pgxpool.New(context.Background(), cfg.DatabaseURL)
		if err != nil {
			fmt.Fprintf(os.Stderr, "broker: db pool error: %v\n", err)
			os.Exit(1)
		}
		resolveStore = resolve.NewPgStore(pool)
	}

	r := chi.NewRouter()
	r.Get("/.well-known/jwks.json", keys.JWKSHandler(ring).ServeHTTP)
	r.Get("/v1/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"status":"ok"}`)
	})

	// POST /v1/api-keys/resolve — internal; called by Egress Proxy only.
	// Source: design §3; ADR-0018 §3; long-lived-api-keys task 4.1.
	r.Post("/v1/api-keys/resolve", resolve.NewHandler(resolveStore, cfg.ProxyServiceToken).ServeHTTP)

	mux := r

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.HTTPPort),
		Handler: mux,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 1)
	go func() {
		log.Printf("broker: HTTP listening on :%d", cfg.HTTPPort)
		errCh <- srv.ListenAndServe()
	}()

	select {
	case <-ctx.Done():
		_ = srv.Shutdown(context.Background())
	case err := <-errCh:
		fmt.Fprintf(os.Stderr, "broker: serve error: %v\n", err)
		os.Exit(1)
	}
	log.Println("broker: shutdown complete")
}
