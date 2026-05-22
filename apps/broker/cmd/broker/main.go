// Credential Broker — Ed25519 key loading + JWKS endpoint + API-key resolve.
//
// Source: design §7; ADR-0006; ADR-0018; T-1.0.5; long-lived-api-keys task 4.1.
package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/packages/go/otelinit"
	"github.com/mintkey/mintkey/packages/go/ulid"
	"github.com/mintkey/mintkey/services/broker/internal/api/issue"
	"github.com/mintkey/mintkey/services/broker/internal/api/resolve"
	"github.com/mintkey/mintkey/services/broker/internal/config"
	"github.com/mintkey/mintkey/services/broker/internal/issuer"
	"github.com/mintkey/mintkey/services/broker/internal/keys"
	"github.com/mintkey/mintkey/services/broker/internal/metrics"
)

func main() {
	cfg := config.Load()

	// Wire OTel SDK with mandatory redaction filter (ADR-0017.6).
	otlpEndpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if otlpEndpoint == "" {
		otlpEndpoint = "otel-collector:4317"
	}
	otelShutdown, err := otelinit.Init(context.Background(), "mintkey/broker", otlpEndpoint)
	if err != nil {
		log.Printf("broker: OTel init warning: %v (continuing without telemetry)", err)
	} else {
		defer func() { _ = otelShutdown(context.Background()) }()
	}

	// Key ring: generate an ephemeral Ed25519 key pair for dev.
	// In T-1.0.8+ the private key is fetched from Vault Adapter using svcid_broker.
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		log.Fatalf("broker: keygen: %v", err)
	}
	activeKID := ulid.New("kid_")
	ring := keys.NewKeyRing()
	ring.Add(activeKID, pub)
	iss := issuer.New(priv, activeKID, ring)
	log.Printf("broker: starting (env=%s, port=%d)", cfg.Env, cfg.HTTPPort)

	// Async audit queue (#22, #27).
	// Replay any events left in the WAL from a previous run, then start the
	// background drainer.  The queue is drained and closed on graceful shutdown.
	// NewWithConfig provides the service label for Prometheus metrics and the
	// WAL compaction policy (timer + size threshold).
	auditQueue := auditq.NewWithConfig(
		cfg.AdminAPIURL, cfg.BrokerSvcToken, cfg.AuditWALPath,
		"broker", cfg.AuditCompact,
	)
	auditQueue.Replay()
	auditQueue.Start()

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

	// Broker metrics: mintkey_token_issued_total (OPS-O).
	m := metrics.New()

	r := chi.NewRouter()
	r.Get("/.well-known/jwks.json", keys.JWKSHandler(ring).ServeHTTP)
	r.Get("/v1/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"status":"ok"}`)
	})

	// /metrics — Prometheus text exposition (#27, OPS-O).
	// Exposes auditq gauges/counters + mintkey_token_issued_total so Prometheus
	// can scrape WAL health metrics and token issuance counts from the broker.
	r.Get("/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
		_, _ = fmt.Fprintf(w,
			"# HELP mintkey_broker_up Broker process is running.\n"+
				"# TYPE mintkey_broker_up gauge\n"+
				"mintkey_broker_up 1\n",
		)
		auditQueue.WriteMetricsTo(w)
		_ = m.WriteTo(w)
	})

	// POST /v1/api-keys/resolve — internal; called by Egress Proxy only.
	// Source: design §3; ADR-0018 §3; long-lived-api-keys task 4.1.
	r.Post("/v1/api-keys/resolve", resolve.NewHandler(resolveStore, cfg.ProxyServiceToken).ServeHTTP)

	// POST /v1/issue — internal; called by MCP Server only.
	// Source: ADR-0006; ADR-0008; T-1.6.x.
	// Audit: token.issued event emitted asynchronously via WAL queue (#22).
	// Metrics: mintkey_token_issued_total counter incremented on success (OPS-O).
	r.Post("/v1/issue", issue.NewHandlerWithAuditAndMetrics(iss, cfg.MCPServiceToken, auditQueue, m).ServeHTTP)

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
	// Drain the audit queue before exit (5s deadline).
	auditQueue.Close()
	log.Println("broker: shutdown complete")
}
