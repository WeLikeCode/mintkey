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

	"github.com/mintkey/mintkey/internal/otelinit"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/credential"
	proxyjwt "github.com/mintkey/mintkey/services/proxy-plugin/internal/jwt"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/vault"
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

	log.Printf("proxy-plugin: starting env=%s vault=%s jwks=%s port=%d",
		cfg.Env, cfg.VaultAddrGRPC, cfg.JWKSEndpoint, cfg.PluginPort)

	vaultClient := vault.NewClient(cfg.VaultAddrGRPC, "")
	jwksLimiter := proxyjwt.NewJWKSRefreshLimiter()

	handler := newProxyHandler(cfg, vaultClient, jwksLimiter)

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.PluginPort),
		Handler: handler,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("proxy-plugin: server error: %v", err)
		}
	}()

	<-ctx.Done()
	shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutCtx)
	log.Println("proxy-plugin: shutdown complete")
}

// proxyHandler is the HTTP handler that validates JWTs, fetches credentials,
// and reverse-proxies to the target backend.
type proxyHandler struct {
	cfg         *config.Config
	vaultClient *vault.Client
	jwksLimiter *proxyjwt.JWKSRefreshLimiter
	// pubKeys is the in-memory JWKS cache: kid → public key.
	pubKeys map[string]ed25519.PublicKey
}

func newProxyHandler(cfg *config.Config, vaultClient *vault.Client, limiter *proxyjwt.JWKSRefreshLimiter) *proxyHandler {
	return &proxyHandler{
		cfg:         cfg,
		vaultClient: vaultClient,
		jwksLimiter: limiter,
		pubKeys:     make(map[string]ed25519.PublicKey),
	}
}

func (h *proxyHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Extract JWT from Authorization header.
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
		http.Error(w, "unauthorized: missing Bearer token", http.StatusUnauthorized)
		return
	}
	tokenStr := strings.TrimPrefix(authHeader, "Bearer ")

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
			http.Error(w, "unauthorized: "+err.Error(), http.StatusUnauthorized)
			return
		}
	}

	// Extract required claims.
	serviceID := audFirst(claims["aud"])
	tenantID, _ := claims["tnt"].(string)
	agentID, _ := claims["sub"].(string)

	if serviceID == "" || tenantID == "" {
		http.Error(w, "unauthorized: missing aud or tnt claim", http.StatusUnauthorized)
		return
	}

	// Fetch credential from Vault Adapter.
	credResp, err := h.vaultClient.GetCredential(r.Context(), vault.GetCredentialRequest{
		TenantID:      tenantID,
		ServiceID:     serviceID,
		CallerActorID: agentID,
	})
	if err != nil {
		log.Printf("proxy-plugin: vault GetCredential error (svc=%s tnt=%s): %v", serviceID, tenantID, err)
		http.Error(w, "bad gateway: vault error", http.StatusBadGateway)
		return
	}
	// Ensure plaintext is zeroed after use regardless of path.
	defer clear(credResp.Plaintext)

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
		http.Error(w, "bad gateway: no target URL", http.StatusBadGateway)
		return
	}

	targetURL, err := url.Parse(target)
	if err != nil {
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
		// Inject the credential (also strips the agent's Authorization header).
		if injectErr := credential.Inject(req, cred); injectErr != nil {
			log.Printf("proxy-plugin: inject error: %v", injectErr)
		}
	}

	proxy.ServeHTTP(w, r)
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
