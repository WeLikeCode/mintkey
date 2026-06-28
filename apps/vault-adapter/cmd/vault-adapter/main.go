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

	// Register the proxy-plugin service identity so the scopeInterceptor allows
	// it to call GetCredential (vault.read) and PutCredential (vault.put).
	// MINTKEY_VAULT_PROXY_IDENTITY_ID defaults to "svcid_proxy"; must match the
	// proxy-plugin's MINTKEY_VAULT_PROXY_IDENTITY_ID env var.
	// MINTKEY_VAULT_PROXY_TOKEN must be a shared secret (≥ 32 bytes) provisioned
	// via a Docker/Kubernetes secret and identical on both sides.
	proxyIdentityID := os.Getenv("MINTKEY_VAULT_PROXY_IDENTITY_ID")
	if proxyIdentityID == "" {
		proxyIdentityID = "svcid_proxy"
	}
	proxyToken := []byte(os.Getenv("MINTKEY_VAULT_PROXY_TOKEN"))
	if len(proxyToken) == 0 {
		log.Printf("vault-adapter: WARNING: MINTKEY_VAULT_PROXY_TOKEN is not set; proxy-plugin credential fetches WILL fail with PERMISSION_DENIED")
	} else {
		if err := svc.RegisterServiceIdentity(proxyIdentityID, proxyToken, []string{"vault.read", "vault.put"}); err != nil {
			fmt.Fprintf(os.Stderr, "vault-adapter: RegisterServiceIdentity(%s): %v\n", proxyIdentityID, err)
			os.Exit(1)
		}
		log.Printf("vault-adapter: registered proxy service identity %q with scopes [vault.read vault.put]", proxyIdentityID)
	}

	// Register the admin-api service identity so the scopeInterceptor allows
	// it to call GetCredential (vault.read), PutCredential (vault.put),
	// PutAgentSecret (vault.secret.put), and DeleteAgentSecret (vault.secret.delete).
	// vault.secret.read is NOT granted — admin-api never reads agent-secret plaintext
	// (least privilege; operators provision secrets but agents own the read path).
	// MINTKEY_VAULT_ADMIN_IDENTITY_ID defaults to "svcid_admin_api"; must match
	// admin-api's MINTKEY_VAULT_ADMIN_IDENTITY_ID env var.
	// MINTKEY_VAULT_ADMIN_TOKEN must be a shared secret (≥ 32 bytes) provisioned
	// via a Docker/Kubernetes secret and identical on both sides.
	adminIdentityID := os.Getenv("MINTKEY_VAULT_ADMIN_IDENTITY_ID")
	if adminIdentityID == "" {
		adminIdentityID = "svcid_admin_api"
	}
	adminToken := []byte(os.Getenv("MINTKEY_VAULT_ADMIN_TOKEN"))
	if len(adminToken) == 0 {
		log.Printf("vault-adapter: WARNING: MINTKEY_VAULT_ADMIN_TOKEN is not set; admin-api credential operations WILL fail with PERMISSION_DENIED")
	} else {
		if err := svc.RegisterServiceIdentity(adminIdentityID, adminToken, []string{"vault.read", "vault.put", "vault.secret.put", "vault.secret.delete"}); err != nil {
			fmt.Fprintf(os.Stderr, "vault-adapter: RegisterServiceIdentity(%s): %v\n", adminIdentityID, err)
			os.Exit(1)
		}
		log.Printf("vault-adapter: registered admin-api service identity %q with scopes [vault.read vault.put vault.secret.put vault.secret.delete]", adminIdentityID)
	}

	// Register the SSH-proxy service identity so the scopeInterceptor allows
	// it to call GetCredential (vault.read). The SSH proxy only reads credentials;
	// it never writes them (vault.put is not granted).
	// MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID defaults to "svcid_ssh_proxy"; must match
	// the ssh-proxy's MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID env var.
	// MINTKEY_VAULT_SSH_PROXY_TOKEN must be a shared secret (≥ 32 bytes) provisioned
	// via a Docker/Kubernetes secret. When not set, SSH proxy credential fetches WILL
	// fail with PERMISSION_DENIED (intentional — unprovisioned env is not a valid state).
	sshProxyIdentityID := os.Getenv("MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID")
	if sshProxyIdentityID == "" {
		sshProxyIdentityID = "svcid_ssh_proxy"
	}
	sshProxyToken := []byte(os.Getenv("MINTKEY_VAULT_SSH_PROXY_TOKEN"))
	if len(sshProxyToken) == 0 {
		log.Printf("vault-adapter: MINTKEY_VAULT_SSH_PROXY_TOKEN not set; SSH proxy credential fetches WILL fail with PERMISSION_DENIED")
	} else {
		// vault.read for GetCredential + GetAgentByFingerprint + GetHostKeyFingerprint
		// vault.put for StoreHostKeyFingerprint (TOFU write)
		if err := svc.RegisterServiceIdentity(sshProxyIdentityID, sshProxyToken, []string{"vault.read", "vault.put"}); err != nil {
			fmt.Fprintf(os.Stderr, "vault-adapter: RegisterServiceIdentity(%s): %v\n", sshProxyIdentityID, err)
			os.Exit(1)
		}
		log.Printf("vault-adapter: registered SSH proxy service identity %q with scopes [vault.read vault.put]", sshProxyIdentityID)
	}

	// Register the email-proxy service identity so ValidateServiceIdentity (and
	// future GetCredential calls) are allowed. Email proxy has vault.read (to
	// fetch email credentials) and vault.put is not needed.
	// MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID defaults to "svcid_email_proxy".
	// MINTKEY_VAULT_EMAIL_PROXY_TOKEN must be a shared secret (≥ 32 bytes)
	// provisioned via a Docker/Kubernetes secret and identical on both sides.
	emailProxyIdentityID := os.Getenv("MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID")
	if emailProxyIdentityID == "" {
		emailProxyIdentityID = "svcid_email_proxy"
	}
	emailProxyToken := []byte(os.Getenv("MINTKEY_VAULT_EMAIL_PROXY_TOKEN"))
	if len(emailProxyToken) == 0 {
		log.Printf("vault-adapter: MINTKEY_VAULT_EMAIL_PROXY_TOKEN not set; email-proxy identity validation WILL fail with PERMISSION_DENIED")
	} else {
		if err := svc.RegisterServiceIdentity(emailProxyIdentityID, emailProxyToken, []string{"vault.read"}); err != nil {
			fmt.Fprintf(os.Stderr, "vault-adapter: RegisterServiceIdentity(%s): %v\n", emailProxyIdentityID, err)
			os.Exit(1)
		}
		log.Printf("vault-adapter: registered email-proxy service identity %q with scopes [vault.read]", emailProxyIdentityID)
	}

	// Register the MCP-server service identity so the scopeInterceptor allows
	// it to call PutAgentSecret (vault.secret.put), GetAgentSecret (vault.secret.read),
	// and DeleteAgentSecret (vault.secret.delete) on the AgentSecretsVault service.
	// MINTKEY_VAULT_MCP_IDENTITY_ID defaults to "svcid_mcp"; must match the
	// mcp-server's MINTKEY_VAULT_MCP_IDENTITY_ID env var.
	// MINTKEY_VAULT_MCP_TOKEN must be a shared secret (≥ 32 bytes) provisioned
	// via a Docker/Kubernetes secret and identical on both sides.
	mcpIdentityID := os.Getenv("MINTKEY_VAULT_MCP_IDENTITY_ID")
	if mcpIdentityID == "" {
		mcpIdentityID = "svcid_mcp"
	}
	mcpToken := []byte(os.Getenv("MINTKEY_VAULT_MCP_TOKEN"))
	if len(mcpToken) == 0 {
		log.Printf("vault-adapter: MINTKEY_VAULT_MCP_TOKEN not set; MCP-server agent-secret operations WILL fail with PERMISSION_DENIED")
	} else {
		if err := svc.RegisterServiceIdentity(mcpIdentityID, mcpToken, []string{"vault.secret.put", "vault.secret.read", "vault.secret.delete"}); err != nil {
			fmt.Fprintf(os.Stderr, "vault-adapter: RegisterServiceIdentity(%s): %v\n", mcpIdentityID, err)
			os.Exit(1)
		}
		log.Printf("vault-adapter: registered MCP service identity %q with scopes [vault.secret.put vault.secret.read vault.secret.delete]", mcpIdentityID)
	}

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
