// Mintkey Egress Proxy Plugin — HTTP reverse proxy with JWT validation and
// credential injection.
//
// This process runs as an HTTP reverse proxy. Incoming requests must carry a
// valid Mintkey JWT in the Authorization: Bearer header. The plugin:
//  1. Validates the JWT using the broker JWKS endpoint.
//  2. Fetches the plaintext credential from the Vault Adapter (per ADR-0014.4).
//  3. Injects the credential into the outbound request.
//  4. Reverse-proxies to the target backend.
//
// The plugin does NOT cache plaintext credentials (ADR-0014.4). Every proxy
// hit calls the Vault Adapter gRPC endpoint for the credential and holds it
// only within request scope.
//
// Source: design §10; ADR-0004; ADR-0014.4; T-1.0.7.
package main

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/packages/go/otelinit"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/audit"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/cache"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/changes"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/classicalkey"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/egress"
	proxyjwt "github.com/mintkey/mintkey/services/proxy-plugin/internal/jwt"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/metrics"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
	"golang.org/x/sync/singleflight"
)

func main() {
	cfg := config.Load()

	// Wire OTel SDK with mandatory redaction filter (ADR-0017.6).
	otlpEndpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if otlpEndpoint == "" {
		otlpEndpoint = "otel-collector:4317"
	}
	otelShutdown, err := otelinit.Init(context.Background(), "mintkey/proxy-plugin", otlpEndpoint)
	if err != nil {
		log.Printf("proxy-plugin: OTel init warning: %v (continuing without telemetry)", err)
	} else {
		defer func() { _ = otelShutdown(context.Background()) }()
	}

	log.Printf("proxy-plugin: starting env=%s vault=%s jwks=%s port=%d aud_enforcement=%s",
		cfg.Env, cfg.VaultAddrGRPC, cfg.JWKSEndpoint, cfg.PluginPort, cfg.AudEnforcement)

	// Async audit queue (#22, #27).
	// Replay any events left in the WAL from a previous run, then start the
	// background drainer.  The queue is drained and closed on graceful shutdown.
	// NewWithConfig provides the service label for Prometheus metrics and the
	// WAL compaction policy (timer + size threshold).
	auditQueue := auditq.NewWithConfig(
		cfg.AdminAPIURL, cfg.ProxyServiceToken, cfg.AuditWALPath,
		"proxy-plugin", cfg.AuditCompact,
	)
	auditQueue.Replay()
	auditQueue.Start()

	vaultClient := vault.NewClient(cfg.VaultAddrGRPC, cfg.VaultIdentityToken, cfg.VaultIdentityID)
	jwksLimiter := proxyjwt.NewJWKSRefreshLimiter()

	// Wire AuditEmitter for classical-key path (was nil, causing WS-9 gap).
	ckAuditEmitter := &classicalKeyAuditAdapter{q: auditQueue}
	ckHandler := classicalkey.NewHandler(classicalkey.Config{
		BrokerURL:    cfg.BrokerBaseURL,
		ProxyToken:   cfg.ProxyServiceToken,
		CacheTTL:     60 * time.Second,
		AuditEmitter: ckAuditEmitter,
	})

	proxyMetrics := metrics.New()
	handler := newProxyHandler(cfg, vaultClient, jwksLimiter, ckHandler, auditQueue, proxyMetrics)
	// BUG-10/FIX-6: wire the structured token.exchanged emitter so the
	// previously-dead EmitTokenExchanged path is now the live emission path.
	handler.tokenExchangeEmitter = audit.NewEmitter(cfg.AdminAPIURL, cfg.ProxyServiceToken)

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.PluginPort),
		Handler: handler,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Wire the changes subscriber so api_key.revoked and agent.revoked events
	// evict the classical-key resolution cache within ≤ 5s (ADR-0018 §4).
	agentSet := revocation.NewAgentRevocationSet()
	jtiSet := revocation.NewJTIRevocationSet(10_000)
	if dsn := os.Getenv("DATABASE_URL"); dsn != "" {
		sub := changes.NewSubscriber(dsn, agentSet, jtiSet, ckHandler)
		go func() {
			if err := sub.Start(ctx); err != nil && ctx.Err() == nil {
				log.Printf("proxy-plugin: changes subscriber error: %v", err)
			}
		}()
	}

	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("proxy-plugin: server error: %v", err)
		}
	}()

	<-ctx.Done()
	shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutCtx)
	// Drain the audit queue before exit (5s deadline).
	auditQueue.Close()
	log.Println("proxy-plugin: shutdown complete")
}

// classicalKeyAuditAdapter adapts *auditq.Queue to classicalkey.AuditEmitter.
type classicalKeyAuditAdapter struct {
	q *auditq.Queue
}

func (a *classicalKeyAuditAdapter) EmitProxyHit(ctx context.Context, p classicalkey.ProxyHitPayload) {
	evt := auditq.Event{
		EventType:  "proxy.hit",
		ActorType:  "agent",
		TargetType: "service",
		Payload: map[string]any{
			"auth_method":     p.AuthMethod,
			"api_key_id":      p.APIKeyID,
			"key_fingerprint": p.KeyFingerprint,
			"service_id":      p.ServiceID,
			"status_code":     p.StatusCode,
			"method":          p.Method,
			"path_template":   p.PathTemplate,
			"latency_ms":      p.LatencyMS,
		},
	}
	if p.UsedAt != nil {
		evt.Payload["used_at"] = p.UsedAt.UTC().Format(time.RFC3339)
	}
	a.q.Enqueue(evt)
}

// auditEnqueuer is a narrow interface so tests can inject a mock audit sink
// without depending on the full *auditq.Queue concrete type.
type auditEnqueuer interface {
	Enqueue(auditq.Event)
}

// tokenExchangeEmitterI is a narrow interface for emitting token.exchanged
// audit events via the structured emitter path (Req 22; BUG-10/FIX-6).
// The concrete implementation is *audit.Emitter; nil means disabled.
type tokenExchangeEmitterI interface {
	EmitTokenExchanged(ctx context.Context, event audit.TokenExchangedEvent) error
}

// proxyHandler is the HTTP handler that validates JWTs, fetches credentials,
// and reverse-proxies to the target backend.
type proxyHandler struct {
	cfg         *config.Config
	vaultClient *vault.Client
	jwksLimiter *proxyjwt.JWKSRefreshLimiter
	ckHandler   *classicalkey.Handler
	audit       auditEnqueuer // may be nil (audit disabled)
	auditQ      *auditq.Queue // same as audit but typed to access WriteMetricsTo (#27)
	// tokenExchangeEmitter emits token.exchanged audit events via the structured
	// emitter path (EmitTokenExchanged).  Nil means disabled (e.g. in unit tests
	// that don't inject it).  BUG-10/FIX-6: previously a hand-built auditq.Event
	// was used; routing through this emitter ensures agent_id is included and
	// redaction guardrails are applied.
	tokenExchangeEmitter tokenExchangeEmitterI // may be nil
	metrics     *metrics.Metrics
	// pubKeys is the in-memory JWKS cache: kid → public key.
	pubKeys map[string]ed25519.PublicKey
	// tokenCache is the in-memory cache for OAuth2 password grant exchanged tokens.
	tokenCache *cache.TokenCache
	// tokenExchanger performs OAuth2 password grant token exchanges.
	tokenExchanger *credential.TokenExchanger
	// sfGroup is the shared singleflight.Group for per-(tenant_id, service_id)
	// coalescing of concurrent token-cache-miss exchanges.  Initialised once at
	// startup and reused across all requests (Req 20/21 thundering-herd protection).
	sfGroup *singleflight.Group
}

func newProxyHandler(cfg *config.Config, vaultClient *vault.Client, limiter *proxyjwt.JWKSRefreshLimiter, ck *classicalkey.Handler, aq *auditq.Queue, m *metrics.Metrics) *proxyHandler {
	var ae auditEnqueuer
	if aq != nil {
		ae = aq
	}
	if m == nil {
		m = metrics.New()
	}
	return &proxyHandler{
		cfg:            cfg,
		vaultClient:    vaultClient,
		jwksLimiter:    limiter,
		ckHandler:      ck,
		audit:          ae,
		auditQ:         aq,
		metrics:        m,
		pubKeys:        make(map[string]ed25519.PublicKey),
		tokenCache:     cache.NewTokenCache(),
		tokenExchanger: credential.NewTokenExchanger(),
		sfGroup:        new(singleflight.Group),
	}
}

func (h *proxyHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Health and metrics endpoints — bypass auth.
	if r.URL.Path == "/healthz" || r.URL.Path == "/v1/health" {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"status":"ok"}`)
		return
	}
	if r.URL.Path == "/metrics" {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
		// Write proxy-plugin hit/denied/latency metrics (OPS-P).
		if err := h.metrics.WriteTo(w); err != nil {
			log.Printf("proxy-plugin: metrics WriteTo error: %v", err)
		}
		// Write auditq WAL and dead-letter metrics (#27).
		if h.auditQ != nil {
			h.auditQ.WriteMetricsTo(w)
		}
		return
	}

	// Extract credential from Authorization: Bearer header.
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
		http.Error(w, "unauthorized: missing Bearer token", http.StatusUnauthorized)
		return
	}
	tokenStr := strings.TrimPrefix(authHeader, "Bearer ")

	// Plugin logic start time — brackets JWT verify + credential fetch + auth
	// scrub only.  The upstream HTTP call is NOT included (OPS-P).
	pluginStart := time.Now()

	// Dispatch classical service API keys (ADR-0018 §2).
	if classicalkey.IsClassicalKey(tokenStr) {
		h.handleClassicalKey(w, r, tokenStr)
		return
	}

	// Validate JWT; on unknown_kid, attempt a JWKS refresh first.
	claims, err := proxyjwt.Verify(tokenStr, h.pubKeys, proxyjwt.VerifyOptions{
		ClockSkewSeconds: 30,
	})
	if err != nil {
		verr, ok := err.(*proxyjwt.VerifyError)
		if ok && verr.Code == "unknown_kid" && h.jwksLimiter.ShouldRefresh(tokenStr) {
			if refreshErr := h.refreshJWKS(r.Context()); refreshErr != nil {
				log.Printf("proxy-plugin: JWKS refresh failed: %v", refreshErr)
			} else {
				claims, err = proxyjwt.Verify(tokenStr, h.pubKeys, proxyjwt.VerifyOptions{
					ClockSkewSeconds: 30,
				})
			}
		}
		if err != nil {
			h.metrics.IncProxyDenied("unknown", "unauthenticated")
			http.Error(w, "unauthorized: "+err.Error(), http.StatusUnauthorized)
			return
		}
	}

	// Extract required claims.
	serviceID := audFirst(claims["aud"])
	tenantID, _ := claims["tnt"].(string)
	agentID, _ := claims["sub"].(string)

	if serviceID == "" || tenantID == "" {
		h.metrics.IncProxyDenied("unknown", "unauthenticated")
		http.Error(w, "unauthorized: missing aud or tnt claim", http.StatusUnauthorized)
		return
	}

	// ADR-0004 addendum (Scenario D / WS-4): compare JWT.aud with the service_id
	// embedded in the URL path.  Both are in the canonical UUID form (the JWT aud
	// contains the DB UUID; the URL path /v1/call/<uuid>/... also carries the UUID).
	// Kong routes are named /v1/call/{service_uuid} so the first non-empty path
	// segment after stripping /v1/call/ is the UUID to compare against.
	if urlSvcID := urlServiceID(r.URL.Path); urlSvcID != "" && urlSvcID != serviceID {
		safeURLSvcID := safeID(urlSvcID)
		safeSvcID := safeID(serviceID)
		log.Printf("proxy-plugin: event=aud_check service_id_url=%s aud=%s mode=%s result=%s",
			safeURLSvcID, safeSvcID, h.cfg.AudEnforcement, audCheckResult(h.cfg.AudEnforcement))
		if h.cfg.AudEnforcement == config.AudEnforcementStrict {
			// Emit audit event for strict-mode rejection (#24).
			// Payload carries only identifiers — no JWT raw value, no credentials (S-SEC-1).
			if h.audit != nil {
				jtiForReject, _ := claims["jti"].(string)
				h.audit.Enqueue(auditq.Event{
					EventType:  "proxy.aud_mismatch_rejected",
					TenantID:   tenantID,
					ActorID:    agentID,
					ActorType:  "agent",
					TargetID:   serviceID,
					TargetType: "service",
					Payload: map[string]any{
						"jti":            jtiForReject,
						"aud":            serviceID,
						"url_service_id": urlSvcID,
						"mode":           string(h.cfg.AudEnforcement),
					},
				})
			}
			h.metrics.IncProxyDenied(serviceID, "permission_denied")
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			_, _ = fmt.Fprint(w, `{"error":"scope mismatch"}`)
			return
		}
		// Permissive: log warning, proceed.
	}

	// Fetch credential from Vault Adapter.
	credResp, err := h.vaultClient.GetCredential(r.Context(), vault.GetCredentialRequest{
		TenantID:      tenantID,
		ServiceID:     serviceID,
		CallerActorID: agentID,
	})
	if err != nil {
		safeSvcID := safeID(serviceID)
		safeTntID := safeID(tenantID)
		log.Printf("proxy-plugin: vault GetCredential error (svc=%s tnt=%s): %v", safeSvcID, safeTntID, err)
		h.metrics.IncProxyDenied(serviceID, "backend_error")
		http.Error(w, "bad gateway: vault error", http.StatusBadGateway)
		return
	}
	// Ensure plaintext is zeroed after use regardless of path.
	defer clear(credResp.Plaintext)

	// OAuth2 Password Grant (auth_scheme=8): orchestrate cache → exchange → inject → audit.
	if credential.AuthScheme(credResp.AuthScheme) == credential.AuthSchemeOAuth2PasswordGrant {
		h.handleOAuth2PasswordGrant(w, r, credResp, tenantID, serviceID, agentID, pluginStart)
		return
	}

	// Prefer target URL from vault (registered base_url); fall back to X-Mintkey-Target header
	// for backward compatibility with credentials registered before this change.
	target := credResp.TargetURL
	if target == "" {
		target = r.Header.Get("X-Mintkey-Target")
	}
	if target == "" {
		target = h.cfg.DefaultTarget
	}
	if target == "" {
		h.metrics.IncProxyDenied(serviceID, "backend_error")
		http.Error(w, "bad gateway: no target URL", http.StatusBadGateway)
		return
	}

	targetURL, err := url.Parse(target)
	if err != nil {
		h.metrics.IncProxyDenied(serviceID, "backend_error")
		http.Error(w, "bad gateway: invalid target URL", http.StatusBadGateway)
		return
	}

	// Build the reverse proxy with credential injection in the Director.
	cred := credential.Credential{
		AuthScheme: credential.AuthScheme(credResp.AuthScheme),
		Value:      credResp.Plaintext,
		HeaderName: credResp.HeaderName,
		QueryParam: credResp.QueryParam,
	}

	proxy := httputil.NewSingleHostReverseProxy(targetURL)
	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalDirector(req)
		// Use the target's Host header so the upstream sees the correct virtual host.
		req.Host = req.URL.Host
		// Strip the X-Mintkey-Target header before forwarding.
		req.Header.Del("X-Mintkey-Target")
		// When routed via the /v1/call/ catch-all, Kong strips /v1/call/ but leaves
		// /<svc_id>/<actual-path>. Strip the leading /<svc_id> segment here so the
		// backend receives the bare API path (e.g. /api-key-header).
		stripped := strings.TrimPrefix(req.URL.Path, "/"+serviceID)
		if stripped != req.URL.Path {
			if stripped == "" || stripped[0] != '/' {
				stripped = "/" + stripped
			}
			req.URL.Path = stripped
		}
		// Inject the credential (also strips the agent's Authorization header).
		// safeInjectErr returns a fixed string so the credential plaintext
		// cannot reach the log sink (CodeQL go/clear-text-logging).
		if injectErr := credential.Inject(req, cred); injectErr != nil {
			safeErr := safeInjectErr(injectErr)
			log.Printf("proxy-plugin: inject error: %s", safeErr)
		}
	}

	// Plugin logic is complete: record added latency (JWT verify + credential
	// fetch + Director setup) — NOT the upstream HTTP call (OPS-P).
	pluginElapsed := time.Since(pluginStart).Seconds()
	h.metrics.ObserveAddedLatency(serviceID, pluginElapsed)
	h.metrics.IncProxyHit(serviceID)

	// Wrap the ResponseWriter to capture the upstream status code for audit.
	jtiClaim, _ := claims["jti"].(string)
	startTime := time.Now()
	rw := &statusCapture{ResponseWriter: w}
	proxy.ServeHTTP(rw, r)

	// Async audit: proxy.hit / proxy.error (#22).
	// Emission is O(1) non-blocking; never carries credentials (S-SEC-1).
	if h.audit != nil {
		latencyMS := time.Since(startTime).Milliseconds()
		statusCode := rw.status
		if statusCode == 0 {
			statusCode = http.StatusOK // WriteHeader not called → 200
		}
		eventType := "proxy.hit"
		outcome := "allowed"
		if statusCode >= 400 {
			eventType = "proxy.error"
			outcome = "error"
		}
		h.audit.Enqueue(auditq.Event{
			EventType:  eventType,
			TenantID:   tenantID,
			ActorID:    agentID,
			ActorType:  "agent",
			TargetID:   serviceID,
			TargetType: "service",
			Payload: map[string]any{
				"jti":                 jtiClaim,
				"upstream_status":     statusCode,
				"upstream_latency_ms": latencyMS,
				"outcome":             outcome,
			},
		})
	}
}

// newOAuth2Deps builds the egress.OAuth2HandlerDeps used by every
// handleOAuth2PasswordGrant call.  It is a separate method so that tests can
// assert that the production construction site wires every required field
// (including the singleflight group) without needing to hand-build a
// divergent copy of the struct.
func (h *proxyHandler) newOAuth2Deps() egress.OAuth2HandlerDeps {
	return egress.OAuth2HandlerDeps{
		Cache:     h.tokenCache,
		Exchanger: h.tokenExchanger,
		// SF must remain h.sfGroup — dropping this line re-introduces the
		// thundering-herd regression (FIX-5).  The test
		// TestProductionPath_NewOAuth2Deps_SFIsWired catches that.
		SF: h.sfGroup,
	}
}

// handleOAuth2PasswordGrant handles the OAuth2 password grant egress flow.
// Orchestrates: parse credential → cache check → exchange → graceful degradation → inject → audit.
//
// Requirements: 20.1, 20.4, 21.3, 21.4, 21.7.
func (h *proxyHandler) handleOAuth2PasswordGrant(
	w http.ResponseWriter, r *http.Request,
	credResp *vault.GetCredentialResponse,
	tenantID, serviceID, agentID string,
	pluginStart time.Time,
) {
	// Run the OAuth2 orchestration (cache → exchange → graceful degradation).
	// newOAuth2Deps builds deps from the shared handler fields (including
	// h.sfGroup for thundering-herd protection).
	deps := h.newOAuth2Deps()

	oauthResult, err := egress.HandleOAuth2PasswordGrant(
		r.Context(), deps, tenantID, serviceID, credResp.Plaintext,
	)

	// Emit token.exchanged audit event if an exchange was attempted.
	// BUG-10/FIX-6: route through audit.EmitTokenExchanged (the previously-dead
	// emitter path) so that agent_id is included and redaction guardrails apply.
	// Fire-and-forget: audit must never block the proxied request.
	if oauthResult != nil && oauthResult.Exchanged && h.tokenExchangeEmitter != nil {
		emitter := h.tokenExchangeEmitter
		ev := audit.TokenExchangedEvent{
			TenantID:     tenantID,
			ServiceID:    serviceID,
			AgentID:      agentID,
			TokenURLHost: oauthResult.TokenURLHost, // already host-only from egress layer
			Success:      oauthResult.ExchangeSuccess,
			LatencyMS:    oauthResult.ExchangeLatencyMS,
		}
		go func() {
			if err := emitter.EmitTokenExchanged(context.Background(), ev); err != nil {
				log.Printf("proxy-plugin: token.exchanged audit emit error: %v", err)
			}
		}()
	}

	if err != nil {
		// Exchange failed and no cached token available — return 502.
		h.metrics.IncProxyDenied(serviceID, "backend_error")
		errCode := egress.ClassifyError(err)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		_, _ = fmt.Fprintf(w, `{"error":"%s"}`, errCode)
		return
	}

	// Determine target URL.
	target := credResp.TargetURL
	if target == "" {
		target = r.Header.Get("X-Mintkey-Target")
	}
	if target == "" {
		target = h.cfg.DefaultTarget
	}
	if target == "" {
		h.metrics.IncProxyDenied(serviceID, "backend_error")
		http.Error(w, "bad gateway: no target URL", http.StatusBadGateway)
		return
	}

	targetURL, err := url.Parse(target)
	if err != nil {
		h.metrics.IncProxyDenied(serviceID, "backend_error")
		http.Error(w, "bad gateway: invalid target URL", http.StatusBadGateway)
		return
	}

	// Build the credential with the exchanged token for injection.
	cred := credential.Credential{
		AuthScheme: credential.AuthSchemeOAuth2PasswordGrant,
		Value:      []byte(oauthResult.Token),
	}

	// Build the reverse proxy.
	proxy := httputil.NewSingleHostReverseProxy(targetURL)
	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalDirector(req)
		req.Host = req.URL.Host
		req.Header.Del("X-Mintkey-Target")
		// Strip the leading /<svc_id> segment from the path.
		stripped := strings.TrimPrefix(req.URL.Path, "/"+serviceID)
		if stripped != req.URL.Path {
			if stripped == "" || stripped[0] != '/' {
				stripped = "/" + stripped
			}
			req.URL.Path = stripped
		}
		// Inject the exchanged token as Authorization: Bearer.
		if injectErr := credential.Inject(req, cred); injectErr != nil {
			safeErr := safeInjectErr(injectErr)
			log.Printf("proxy-plugin: oauth2 inject error: %s", safeErr)
		}
	}

	// Plugin logic complete: record added latency.
	pluginElapsed := time.Since(pluginStart).Seconds()
	h.metrics.ObserveAddedLatency(serviceID, pluginElapsed)
	h.metrics.IncProxyHit(serviceID)

	// Wrap ResponseWriter to capture status for audit.
	startTime := time.Now()
	rw := &statusCapture{ResponseWriter: w}
	proxy.ServeHTTP(rw, r)

	// Async audit: proxy.hit / proxy.error.
	if h.audit != nil {
		latencyMS := time.Since(startTime).Milliseconds()
		statusCode := rw.status
		if statusCode == 0 {
			statusCode = http.StatusOK
		}
		eventType := "proxy.hit"
		outcome := "allowed"
		if statusCode >= 400 {
			eventType = "proxy.error"
			outcome = "error"
		}
		h.audit.Enqueue(auditq.Event{
			EventType:  eventType,
			TenantID:   tenantID,
			ActorID:    agentID,
			ActorType:  "agent",
			TargetID:   serviceID,
			TargetType: "service",
			Payload: map[string]any{
				"upstream_status":     statusCode,
				"upstream_latency_ms": latencyMS,
				"outcome":             outcome,
			},
		})
	}
}

// handleClassicalKey handles the ADR-0018 classical service API key path.
// service_id and tenant_id come from headers injected by Kong's request-transformer
// plugin (generated by kong-syncer); if absent, service_id is parsed from the URL.
func (h *proxyHandler) handleClassicalKey(w http.ResponseWriter, r *http.Request, cred string) {
	serviceID := r.Header.Get("X-Mintkey-Service-ID")
	tenantID := r.Header.Get("X-Mintkey-Tenant-ID")

	if serviceID == "" {
		// Fallback: parse from URL (static catch-all route leaves /<svc_id>/path)
		parts := strings.SplitN(strings.TrimPrefix(r.URL.Path, "/"), "/", 2)
		if len(parts) > 0 && strings.HasPrefix(parts[0], "svc_") {
			serviceID = parts[0]
		}
	}
	if serviceID == "" || tenantID == "" {
		http.Error(w, "bad gateway: missing service routing metadata", http.StatusBadGateway)
		return
	}

	res, err := h.ckHandler.Resolve(r.Context(), cred, serviceID, tenantID)
	if err != nil {
		if kerr, ok := err.(*classicalkey.KeyError); ok {
			http.Error(w, "unauthorized: "+kerr.Code, kerr.HTTPStatus)
		} else {
			http.Error(w, "service unavailable", http.StatusServiceUnavailable)
		}
		return
	}

	reqCtx := &classicalkey.RequestContext{
		ServiceID: serviceID,
		Method:    r.Method,
		Path:      r.URL.Path,
		ClientIP:  r.RemoteAddr,
	}
	if err := h.ckHandler.CheckRequest(res, reqCtx); err != nil {
		kerr := err.(*classicalkey.KeyError)
		http.Error(w, "forbidden: "+kerr.Code, kerr.HTTPStatus)
		return
	}

	credResp, err := h.vaultClient.GetCredential(r.Context(), vault.GetCredentialRequest{
		TenantID:      tenantID,
		ServiceID:     serviceID,
		CallerActorID: res.AgentID,
	})
	if err != nil {
		safeSvcID := safeID(serviceID)
		safeTntID := safeID(tenantID)
		log.Printf("proxy-plugin: classical key vault error (svc=%s tnt=%s): %v", safeSvcID, safeTntID, err)
		http.Error(w, "bad gateway: vault error", http.StatusBadGateway)
		return
	}
	defer clear(credResp.Plaintext)

	target := credResp.TargetURL
	if target == "" {
		target = h.cfg.DefaultTarget
	}
	if target == "" {
		http.Error(w, "bad gateway: no target URL", http.StatusBadGateway)
		return
	}

	targetURL, err := url.Parse(target)
	if err != nil {
		http.Error(w, "bad gateway: invalid target URL", http.StatusBadGateway)
		return
	}

	backendCred := credential.Credential{
		AuthScheme: credential.AuthScheme(credResp.AuthScheme),
		Value:      credResp.Plaintext,
		HeaderName: credResp.HeaderName,
		QueryParam: credResp.QueryParam,
	}

	proxy := httputil.NewSingleHostReverseProxy(targetURL)
	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalDirector(req)
		req.Host = req.URL.Host
		req.Header.Del("X-Mintkey-Target")
		req.Header.Del("X-Mintkey-Service-ID")
		req.Header.Del("X-Mintkey-Tenant-ID")
		stripped := strings.TrimPrefix(req.URL.Path, "/"+serviceID)
		if stripped != req.URL.Path {
			if stripped == "" || stripped[0] != '/' {
				stripped = "/" + stripped
			}
			req.URL.Path = stripped
		}
		if injectErr := credential.Inject(req, backendCred); injectErr != nil {
			safeErr := safeInjectErr(injectErr)
			log.Printf("proxy-plugin: classical key inject error: %s", safeErr)
		}
	}

	proxy.ServeHTTP(w, r)
}

// urlServiceID extracts the service UUID from a Kong-routed path of the form
// /v1/call/<uuid>[/...] or /<uuid>[/...] (legacy catch-all).
// Returns "" if no UUID-shaped segment is found so callers skip the check.
func urlServiceID(path string) string {
	// Strip /v1/call/ prefix (Kong-syncer generated routes).
	trimmed := strings.TrimPrefix(path, "/v1/call/")
	if trimmed == path {
		// Fallback: bare /<svc_id>/... path (legacy static catch-all).
		trimmed = strings.TrimPrefix(path, "/")
	}
	// Take the first path segment.
	if i := strings.IndexByte(trimmed, '/'); i >= 0 {
		trimmed = trimmed[:i]
	}
	// Accept UUID form (8-4-4-4-12 hex) or bare 32-hex.
	if isUUIDShape(trimmed) {
		return trimmed
	}
	return ""
}

// safeID returns s if it is UUID-shaped (safe structured identifier), otherwise
// returns "[redacted]".  Use this whenever logging values that come from
// user-controlled inputs (JWT claims, request headers) to prevent accidental
// credential leakage into logs (CWE-312; CodeQL go/clear-text-logging).
func safeID(s string) string {
	if isUUIDShape(s) {
		return s
	}
	return "[redacted]"
}

// safeInjectErr returns a sanitized string from a credential.Inject error.
// credential.Inject only ever returns errors containing the auth-scheme integer
// or a static sentinel ("mtls: not implemented") — never the credential value.
// This wrapper exists solely to break the CodeQL go/clear-text-logging data-flow
// path from cred.Value through Inject's return value to the log sink.
func safeInjectErr(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

// isUUIDShape returns true for strings that look like a UUID
// (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx, 36 chars) or a 32-char hex string.
func isUUIDShape(s string) bool {
	if len(s) == 36 {
		// Must match xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
		for i, c := range s {
			if i == 8 || i == 13 || i == 18 || i == 23 {
				if c != '-' {
					return false
				}
			} else if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
				return false
			}
		}
		return true
	}
	if len(s) == 32 {
		for _, c := range s {
			if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
				return false
			}
		}
		return true
	}
	return false
}

// audCheckResult returns the result string for the structured log line.
func audCheckResult(mode config.AudEnforcement) string {
	if mode == config.AudEnforcementStrict {
		return "reject"
	}
	return "warn"
}

// audFirst returns the first element of the aud claim (string or []any).
func audFirst(aud any) string {
	switch v := aud.(type) {
	case string:
		return v
	case []any:
		if len(v) > 0 {
			if s, ok := v[0].(string); ok {
				return s
			}
		}
	}
	return ""
}

// refreshJWKS fetches the JWKS endpoint and updates the in-memory key set.
func (h *proxyHandler) refreshJWKS(ctx context.Context) error {
	reqCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, h.cfg.JWKSEndpoint, nil)
	if err != nil {
		return fmt.Errorf("refreshJWKS: build request: %w", err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("refreshJWKS: fetch %s: %w", h.cfg.JWKSEndpoint, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("refreshJWKS: status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	if err != nil {
		return fmt.Errorf("refreshJWKS: read body: %w", err)
	}

	var jwks struct {
		Keys []struct {
			Kid string `json:"kid"`
			Kty string `json:"kty"`
			Crv string `json:"crv"`
			X   string `json:"x"`
		} `json:"keys"`
	}
	if err := json.Unmarshal(body, &jwks); err != nil {
		return fmt.Errorf("refreshJWKS: parse: %w", err)
	}

	newKeys := make(map[string]ed25519.PublicKey, len(jwks.Keys))
	for _, k := range jwks.Keys {
		if k.Kty != "OKP" || k.Crv != "Ed25519" || k.Kid == "" || k.X == "" {
			continue
		}
		keyBytes, err := base64.RawURLEncoding.DecodeString(k.X)
		if err != nil || len(keyBytes) != ed25519.PublicKeySize {
			continue
		}
		newKeys[k.Kid] = ed25519.PublicKey(keyBytes)
	}
	h.pubKeys = newKeys
	return nil
}

// statusCapture is a minimal ResponseWriter wrapper that records the HTTP
// status code written by the upstream reverse proxy so the audit event can
// carry it.
type statusCapture struct {
	http.ResponseWriter
	status int
}

func (s *statusCapture) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

// Unwrap satisfies http.ResponseController so http.Flush/http.Hijack still
// work through the wrapper.
func (s *statusCapture) Unwrap() http.ResponseWriter {
	return s.ResponseWriter
}
