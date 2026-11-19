// Vault Adapter — KEK loading + gRPC server startup.
//
// Source: design §8; ADR-0003; T-1.0.4.
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/mintkey/mintkey/packages/go/otelinit"
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

	st, err := store.NewFromEnv(context.Background())
	if err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: store: %v\n", err)
		os.Exit(1)
	}
	backendName := os.Getenv("MINTKEY_VAULT_BACKEND")
	if backendName == "" {
		backendName = "postgres"
	}
	log.Printf("vault-adapter: store backend = %s", backendName)

	// NewVaultService shares dekCache so the changes subscriber and the vault
	// service operate on the same in-process cache instance (metrics and
	// invalidations reflect the same state).
	svc := server.NewVaultService(key, st, dekCache)
	srv := server.New(key, dekCache)

	unset, err := svc.RegisterBootIdentitiesFromEnv(cfg.Env)
	if err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: fatal: %v\n", err)
		os.Exit(1)
	}
	for _, name := range unset {
		log.Printf("vault-adapter: WARNING: %s is not set; that identity is not registered and its calls fail with PERMISSION_DENIED", name)
	}
	log.Printf("vault-adapter: registered %d of %d boot identities", len(server.BootIdentities)-len(unset), len(server.BootIdentities))

	// Wire the SSHStore so ListenAndServe registers the SSHVaultAdapter service.
	// Only PostgresStore implements SSHStore; SQLite falls back to no SSH RPCs.
	if pgStore, ok := st.(*store.PostgresStore); ok {
		srv.WithSSHStore(pgStore)
		log.Printf("vault-adapter: SSHVaultAdapter service enabled (postgres backend)")
	} else {
		log.Printf("vault-adapter: SSHVaultAdapter service disabled (non-postgres backend)")
	}

	// Wire the AgentSecretStore so ListenAndServe registers the AgentSecretsVault service.
	// Only PostgresStore implements AgentSecretStore; SQLite falls back to no AgentSecretsVault RPCs.
	if pgStore, ok := st.(*store.PostgresStore); ok {
		srv.WithAgentSecretStore(pgStore)
		log.Printf("vault-adapter: AgentSecretsVault service enabled (postgres backend)")
	} else {
		log.Printf("vault-adapter: AgentSecretsVault service disabled (non-postgres backend)")
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// sub may remain nil when MINTKEY_POSTGRES_DSN is not set; the metrics
	// handler checks for nil before calling sub.LagSeconds().
	var sub *changes.Subscriber

	// Start the credential-rotation subscriber if a Postgres DSN is provided.
	if dsn := os.Getenv("MINTKEY_POSTGRES_DSN"); dsn != "" {
		sub = changes.NewSubscriber(dsn, dekCache)
		go func() {
			if err := sub.Start(ctx); err != nil && ctx.Err() == nil {
				log.Printf("vault-adapter: changes subscriber error: %v", err)
			}
		}()
		log.Printf("vault-adapter: credential rotation subscriber started")
	} else {
		log.Printf("vault-adapter: MINTKEY_POSTGRES_DSN not set; credential rotation subscriber disabled")
	}

	// Start HTTP server for health checks and Prometheus metrics.
	httpMux := http.NewServeMux()
	httpMux.HandleFunc("/v1/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"status":"ok"}`)
	})
	httpMux.HandleFunc("/metrics", func(w http.ResponseWriter, _ *http.Request) {
		hits := dekCache.Hits()
		misses := dekCache.Misses()

		var lagSeconds float64
		if sub != nil {
			lagSeconds = sub.LagSeconds()
		}

		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		_, _ = fmt.Fprintf(w,
			"# HELP mintkey_vault_adapter_requests_total Total gRPC requests handled.\n"+
				"# TYPE mintkey_vault_adapter_requests_total counter\n"+
				"mintkey_vault_adapter_requests_total 0\n"+
				"# HELP mintkey_vault_dek_cache_hit_total DEK cache hits.\n"+
				"# TYPE mintkey_vault_dek_cache_hit_total counter\n"+
				"mintkey_vault_dek_cache_hit_total %d\n"+
				"# HELP mintkey_vault_dek_cache_miss_total DEK cache misses.\n"+
				"# TYPE mintkey_vault_dek_cache_miss_total counter\n"+
				"mintkey_vault_dek_cache_miss_total %d\n"+
				"# HELP mintkey_changes_subscriber_lag_seconds Seconds since last change message.\n"+
				"# TYPE mintkey_changes_subscriber_lag_seconds gauge\n"+
				"mintkey_changes_subscriber_lag_seconds %g\n",
			hits, misses, lagSeconds,
		)
	})
	httpSrv := &http.Server{Addr: fmt.Sprintf(":%d", cfg.HTTPPort), Handler: httpMux}
	go func() {
		log.Printf("vault-adapter: HTTP listening on :%d", cfg.HTTPPort)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("vault-adapter: HTTP server error: %v", err)
		}
	}()

	log.Printf("vault-adapter: gRPC listening on :%d", cfg.GRPCPort)
	if err := srv.ListenAndServe(ctx, cfg.GRPCPort, svc); err != nil {
		fmt.Fprintf(os.Stderr, "vault-adapter: serve error: %v\n", err)
		os.Exit(1)
	}
	_ = httpSrv.Shutdown(context.Background())
	log.Println("vault-adapter: shutdown complete")
}
