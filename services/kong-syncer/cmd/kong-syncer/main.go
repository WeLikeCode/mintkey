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

	"github.com/mintkey/mintkey/internal/otelinit"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/changes"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/config"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/health"
)

func main() {
	cfg := config.Load()

	// Wire OTel SDK with mandatory redaction filter (ADR-0017.6).
	otlpEndpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if otlpEndpoint == "" {
		otlpEndpoint = "otel-collector:4317"
	}
	otelShutdown, err := otelinit.Init(context.Background(), "mintkey/kong-syncer", otlpEndpoint)
	if err != nil {
		log.Printf("kong-syncer: OTel init warning: %v (continuing without telemetry)", err)
	} else {
		defer func() { _ = otelShutdown(context.Background()) }()
	}

	log.Printf("kong-syncer: starting (env=%s, port=%d)", cfg.Env, cfg.HTTPPort)

	// Changes subscriber: kong-syncer is a global subscriber (AllTenants).
	// WithTenantScope is required per ADR-0014.1; omitting it panics on Start.
	// Pass DATABASE_URL as a string so the subscriber can LISTEN on mintkey:service.
	sub := changes.NewClient(
		cfg.DatabaseURL,
		changes.WithTenantScope(changes.AllTenants),
		changes.WithKongAdminURL(cfg.KongAdminURL),
	)

	mux := http.NewServeMux()
	mux.Handle("GET /v1/health", health.Handler())
	mux.HandleFunc("GET /metrics", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		_, _ = fmt.Fprint(w,
			"# HELP mintkey_kong_syncer_pushes_total Total Kong config pushes.\n"+
				"# TYPE mintkey_kong_syncer_pushes_total counter\n"+
				"mintkey_kong_syncer_pushes_total 0\n",
		)
	})

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
