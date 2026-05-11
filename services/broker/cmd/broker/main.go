// Credential Broker — Ed25519 key loading + JWKS endpoint.
//
// Source: design §7; ADR-0006; T-1.0.5.
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/mintkey/mintkey/services/broker/internal/config"
	"github.com/mintkey/mintkey/services/broker/internal/keys"
)

func main() {
	cfg := config.Load()

	// Key ring: in the skeleton, load from env or fail.
	// In T-1.0.8+ the private key is fetched from Vault Adapter using svcid_broker.
	ring := keys.NewKeyRing()
	log.Printf("broker: starting (env=%s, port=%d)", cfg.Env, cfg.HTTPPort)

	mux := http.NewServeMux()
	mux.Handle("GET /.well-known/jwks.json", keys.JWKSHandler(ring))
	mux.HandleFunc("GET /v1/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"status":"ok"}`)
	})

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
