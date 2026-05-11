// Package classicalkey implements the Egress Proxy classical-key branch.
//
// When the inbound credential has the mk_svckey_ prefix, this package
// resolves it against the Broker (with in-memory caching), runs per-request
// checks, and provides the OTel attributes and proxy.hit payloads required
// by ADR-0018 §2.
//
// Sources: design §2; Req 2.1–2.4, 2.6, 4.2, 4.4, 6.1–6.4, 10.3, 10.5, 10.6.
package classicalkey

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"go.opentelemetry.io/otel/attribute"
)

// IsClassicalKey reports whether cred is a classical service API key.
// (design §2.1; Req 2.1)
func IsClassicalKey(cred string) bool {
	return strings.HasPrefix(cred, "mk_svckey_")
}

// Fingerprint computes hex(sha256(cred)[:8]) — the lookup key for the cache
// and for the Broker call. (design §2.2; ADR-0018 §2)
func Fingerprint(cred string) string {
	h := sha256.Sum256([]byte(cred))
	return hex.EncodeToString(h[:8])
}

// KeyError is the structured error returned by Resolve and CheckRequest.
type KeyError struct {
	Code       string // mintkey:code value
	HTTPStatus int    // HTTP status to relay to the caller
}

func (e *KeyError) Error() string { return fmt.Sprintf("%s (HTTP %d)", e.Code, e.HTTPStatus) }

// Resolution holds the result of a successful key lookup.
type Resolution struct {
	APIKeyID       string
	AgentID        string
	ServiceID      string
	AllowedActions []string
	Constraints    map[string]any
	ExpiresAt      *time.Time
	Fingerprint    string
}

// ProxyHitPayload is the data for a proxy.hit audit event (design §2.5).
type ProxyHitPayload struct {
	AuthMethod     string
	APIKeyID       string
	KeyFingerprint string
	ServiceID      string
	StatusCode     int
	Method         string
	PathTemplate   string
	LatencyMS      int
	UsedAt         *time.Time
}

// AuditEmitter is the interface for emitting proxy.hit audit events.
type AuditEmitter interface {
	EmitProxyHit(ctx context.Context, p ProxyHitPayload)
}

// RequestContext holds per-request data for CheckRequest.
type RequestContext struct {
	ServiceID       string
	Method          string
	Path            string
	ClientIP        string
	RequestedAction string // if empty, derived from method+path
}

// Config holds dependencies for the classical-key handler.
type Config struct {
	BrokerURL    string
	ProxyToken   string
	CacheTTL     time.Duration
	AuditEmitter AuditEmitter
}

// Handler manages the resolution cache and per-request logic.
type Handler struct {
	cfg      Config
	cache    *resolutionCache
	usedAt   *usedAtTracker
	client   *http.Client
}

// NewHandler constructs a Handler and starts the background sweep goroutine.
func NewHandler(cfg Config) *Handler {
	h := &Handler{
		cfg:    cfg,
		cache:  newResolutionCache(),
		usedAt: newUsedAtTracker(),
		client: &http.Client{Timeout: 5 * time.Second},
	}
	go h.sweepLoop()
	return h
}

// Resolve looks up the resolution for cred (cache-first, then broker).
// Returns (*Resolution, nil) on success; (*KeyError, nil) on auth failure;
// error on unexpected failure.
func (h *Handler) Resolve(ctx context.Context, cred, serviceID, tenantID string) (*Resolution, error) {
	fp := Fingerprint(cred)

	if res := h.cache.get(fp, h.cfg.CacheTTL); res != nil {
		return res, nil
	}

	res, err := h.callBroker(ctx, fp, cred, serviceID, tenantID)
	if err != nil {
		return nil, err
	}
	h.cache.set(fp, res)
	return res, nil
}

// CheckRequest runs the per-request checks in design §2.3 order.
func (h *Handler) CheckRequest(res *Resolution, req *RequestContext) error {
	// 1. Service binding.
	if res.ServiceID != req.ServiceID {
		h.cache.evictByFingerprint(res.Fingerprint)
		return &KeyError{Code: "api_key_wrong_service", HTTPStatus: http.StatusUnauthorized}
	}

	// 2. Expiry.
	if res.ExpiresAt != nil && time.Now().After(*res.ExpiresAt) {
		h.cache.evictByFingerprint(res.Fingerprint)
		return &KeyError{Code: "api_key_expired", HTTPStatus: http.StatusUnauthorized}
	}

	// 3. Action check.
	action := req.RequestedAction
	if action == "" {
		action = deriveAction(req.Method, req.Path)
	}
	if !actionAllowed(action, res.AllowedActions) {
		return &KeyError{Code: "api_key_action_not_allowed", HTTPStatus: http.StatusForbidden}
	}

	// 4. Constraints.
	if err := checkConstraints(res.Constraints, req); err != nil {
		return err
	}

	return nil
}

// EvictByFingerprint removes a cache entry by fingerprint (for api_key.revoked).
func (h *Handler) EvictByFingerprint(fp string) { h.cache.evictByFingerprint(fp) }

// EvictByAgentID removes all cache entries for an agent (for agent.revoked).
func (h *Handler) EvictByAgentID(agentID string) { h.cache.evictByAgentID(agentID) }

// EmitHit emits a proxy.hit audit event with classical-key fields.
// Coalesces used_at: only sets it if >60s since last report for this api_key_id (Req 10.5).
func (h *Handler) EmitHit(ctx context.Context, res *Resolution, cred, serviceID string, statusCode int, method, path string, latencyMS int) error {
	if h.cfg.AuditEmitter == nil {
		return nil
	}
	p := ProxyHitPayload{
		AuthMethod:     "api_key",
		APIKeyID:       res.APIKeyID,
		KeyFingerprint: Fingerprint(cred),
		ServiceID:      serviceID,
		StatusCode:     statusCode,
		Method:         method,
		PathTemplate:   path,
		LatencyMS:      latencyMS,
	}
	if h.usedAt.shouldReport(res.APIKeyID) {
		now := time.Now()
		p.UsedAt = &now
	}
	h.cfg.AuditEmitter.EmitProxyHit(ctx, p)
	return nil
}

// SpanAttributesForClassicalKey returns the OTel attributes for the classical-key path.
// key_fingerprint is NOT included (Req 11.4; design §2.5).
func SpanAttributesForClassicalKey() []attribute.KeyValue {
	return []attribute.KeyValue{
		attribute.String("mintkey.auth_method", "api_key"),
	}
}

// --- internal ---

type cachedEntry struct {
	res      *Resolution
	cachedAt time.Time
}

type resolutionCache struct {
	mu sync.Mutex
	m  map[string]*cachedEntry
}

func newResolutionCache() *resolutionCache {
	return &resolutionCache{m: make(map[string]*cachedEntry)}
}

func (c *resolutionCache) get(fp string, ttl time.Duration) *Resolution {
	c.mu.Lock()
	defer c.mu.Unlock()
	e, ok := c.m[fp]
	if !ok || time.Since(e.cachedAt) >= ttl {
		return nil
	}
	return e.res
}

func (c *resolutionCache) set(fp string, res *Resolution) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.m[fp] = &cachedEntry{res: res, cachedAt: time.Now()}
}

func (c *resolutionCache) evictByFingerprint(fp string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.m, fp)
}

func (c *resolutionCache) evictByAgentID(agentID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for fp, e := range c.m {
		if e.res.AgentID == agentID {
			delete(c.m, fp)
		}
	}
}

func (c *resolutionCache) sweepOlderThan(ttl time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for fp, e := range c.m {
		if time.Since(e.cachedAt) >= ttl {
			delete(c.m, fp)
		}
	}
}

// sweepLoop runs the background TTL sweep every 60 s (design §2.7).
func (h *Handler) sweepLoop() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		h.cache.sweepOlderThan(h.cfg.CacheTTL)
	}
}

// usedAtTracker coalesces the used_at reports — emits at most once per 60s per key.
type usedAtTracker struct {
	mu   sync.Mutex
	last map[string]time.Time
}

func newUsedAtTracker() *usedAtTracker {
	return &usedAtTracker{last: make(map[string]time.Time)}
}

func (t *usedAtTracker) shouldReport(apiKeyID string) bool {
	t.mu.Lock()
	defer t.mu.Unlock()
	if last, ok := t.last[apiKeyID]; ok && time.Since(last) < 60*time.Second {
		return false
	}
	t.last[apiKeyID] = time.Now()
	return true
}

// callBroker posts to the Broker's resolve endpoint.
func (h *Handler) callBroker(ctx context.Context, fp, cred, serviceID, tenantID string) (*Resolution, error) {
	body := map[string]string{
		"key_fingerprint": fp,
		"presented_key":   cred,
		"service_id":      serviceID,
		"tenant_id":       tenantID,
	}
	b, _ := json.Marshal(body)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, h.cfg.BrokerURL+"/v1/api-keys/resolve", bytes.NewReader(b))
	if err != nil {
		return nil, &KeyError{Code: "api_key_resolution_unavailable", HTTPStatus: http.StatusServiceUnavailable}
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", h.cfg.ProxyToken)

	resp, err := h.client.Do(req)
	if err != nil {
		return nil, &KeyError{Code: "api_key_resolution_unavailable", HTTPStatus: http.StatusServiceUnavailable}
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		var r struct {
			APIKeyID       string         `json:"api_key_id"`
			AgentID        string         `json:"agent_id"`
			ServiceID      string         `json:"service_id"`
			AllowedActions []string       `json:"allowed_actions"`
			Constraints    map[string]any `json:"constraints"`
			ExpiresAt      *time.Time     `json:"expires_at"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&r); err != nil {
			return nil, &KeyError{Code: "api_key_resolution_unavailable", HTTPStatus: http.StatusServiceUnavailable}
		}
		return &Resolution{
			APIKeyID:       r.APIKeyID,
			AgentID:        r.AgentID,
			ServiceID:      r.ServiceID,
			AllowedActions: r.AllowedActions,
			Constraints:    r.Constraints,
			ExpiresAt:      r.ExpiresAt,
			Fingerprint:    fp,
		}, nil
	}

	// 4xx → relay the error code; 5xx → unavailable.
	if resp.StatusCode >= 400 && resp.StatusCode < 500 {
		var e struct {
			Code string `json:"mintkey:code"`
		}
		_ = json.NewDecoder(resp.Body).Decode(&e)
		if e.Code == "" {
			e.Code = "api_key_invalid"
		}
		return nil, &KeyError{Code: e.Code, HTTPStatus: resp.StatusCode}
	}
	return nil, &KeyError{Code: "api_key_resolution_unavailable", HTTPStatus: http.StatusServiceUnavailable}
}

// deriveAction derives an action string from the HTTP method and path.
// MVP: uses method-based heuristics; real mapping comes from service config.
func deriveAction(method, path string) string {
	switch strings.ToUpper(method) {
	case "GET", "HEAD":
		return "read:" + strings.TrimPrefix(strings.SplitN(path, "/", 3)[1], "")
	default:
		return "write:" + strings.TrimPrefix(strings.SplitN(path, "/", 3)[1], "")
	}
}

// actionAllowed reports whether action is in the allowed set.
func actionAllowed(action string, allowed []string) bool {
	for _, a := range allowed {
		if a == action {
			return true
		}
	}
	return false
}

// checkConstraints evaluates each present constraint kind (design §2.3 step 4).
func checkConstraints(constraints map[string]any, req *RequestContext) error {
	if constraints == nil {
		return nil
	}

	if cidrList, ok := constraints["source_ip_allowlist"]; ok {
		if !ipInCIDRList(req.ClientIP, cidrList) {
			return &KeyError{Code: "api_key_constraint_failed", HTTPStatus: http.StatusForbidden}
		}
	}

	if prefixes, ok := constraints["request_path_prefix"]; ok {
		if !pathMatchesPrefix(req.Path, prefixes) {
			return &KeyError{Code: "api_key_constraint_failed", HTTPStatus: http.StatusForbidden}
		}
	}

	return nil
}

func ipInCIDRList(clientIP string, list any) bool {
	ip := net.ParseIP(clientIP)
	if ip == nil {
		return false
	}
	cidrs, ok := list.([]any)
	if !ok {
		return false
	}
	for _, c := range cidrs {
		cidr, ok := c.(string)
		if !ok {
			continue
		}
		_, network, err := net.ParseCIDR(cidr)
		if err != nil {
			continue
		}
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

func pathMatchesPrefix(path string, prefixes any) bool {
	list, ok := prefixes.([]any)
	if !ok {
		return false
	}
	for _, p := range list {
		prefix, ok := p.(string)
		if !ok {
			continue
		}
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}
