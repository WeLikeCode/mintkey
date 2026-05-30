// Package audit sends proxy.hit audit events to the admin-api internal endpoint.
//
// Design constraints (T-1.6.5; ADR-0014.7; S-SEC-1):
//   - The HitEvent payload MUST NOT contain any credential value.
//   - Audit emission is fire-and-forget: a non-2xx response logs a warning but
//     NEVER blocks or fails the proxied request.
//   - A 1-second context timeout is applied to every audit HTTP call so that a
//     slow admin-api cannot stall traffic.
//   - An OTel span named "mintkey.proxy.handle_request" is started around the
//     full operation, carrying agent_id, service_id, and tenant_id attributes.
//
// Source: T-1.6.5; ADR-0001; ADR-0014.7; S-SEC-1.
package audit

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

const tracerName = "github.com/mintkey/mintkey/services/proxy-plugin/internal/audit"

// Emitter sends proxy.hit audit events to admin-api's internal endpoint.
// It uses the svcid_proxy boot secret in the X-Mintkey-Service-Token header.
//
// Audit emission is non-blocking: errors are logged as warnings and do NOT
// propagate to the caller (audit must not block traffic).
type Emitter struct {
	adminAPIURL  string
	serviceToken string
	httpClient   *http.Client
}

// TokenExchangedEvent is the payload for a token.exchanged audit record.
//
// Emitted after every token exchange attempt (success or failure).
// Security constraints (Requirements 22.1, 22.2, 22.3, 22.7):
//   - token_url_host contains ONLY the hostname (no path, no query, no credentials)
//   - No credential_fields values in the event
//   - No token value in the event
type TokenExchangedEvent struct {
	TenantID     string `json:"tenant_id"`
	ServiceID    string `json:"service_id"`
	AgentID      string `json:"agent_id"`
	TokenURLHost string `json:"token_url_host"` // host only, path redacted
	Success      bool   `json:"success"`
	LatencyMS    int64  `json:"latency_ms"`
}

// HitEvent is the payload for a proxy.hit audit record.
//
// Field selection is intentional: no credential, api_key, secret, or
// token_value fields are present (S-SEC-1).
type HitEvent struct {
	JTI                 string `json:"jti"`
	AgentID             string `json:"agent_id"`
	ServiceID           string `json:"service_id"`
	TenantID            string `json:"tenant_id"`
	Action              string `json:"action"`
	RequestMethod       string `json:"request_method"`
	RequestPathTemplate string `json:"request_path_template"`
	StatusCode          int    `json:"status_code"`
	LatencyMS           int64  `json:"latency_ms"`
	Outcome             string `json:"outcome"` // "allowed" | "denied" | "error"
}

// NewEmitter creates an Emitter targeting the given adminAPIURL.
// serviceToken is the svcid_proxy boot secret sent on every request.
func NewEmitter(adminAPIURL, serviceToken string) *Emitter {
	return &Emitter{
		adminAPIURL:  adminAPIURL,
		serviceToken: serviceToken,
		httpClient:   &http.Client{Timeout: 5 * time.Second},
	}
}

// EmitHit starts an OTel span, then POSTs a proxy.hit audit event to
// admin-api's /v1/internal/audit/emit endpoint.
//
// A non-2xx response logs a warning and returns an error, but the error is
// informational — callers should not fail the proxied request on audit errors.
func (e *Emitter) EmitHit(ctx context.Context, event HitEvent) error {
	// Start OTel span for the full proxy handle_request operation.
	tracer := otel.GetTracerProvider().Tracer(tracerName)
	ctx, span := tracer.Start(ctx, "mintkey.proxy.handle_request",
		trace.WithSpanKind(trace.SpanKindInternal),
		trace.WithAttributes(
			attribute.String("agent_id", event.AgentID),
			attribute.String("service_id", event.ServiceID),
			attribute.String("tenant_id", event.TenantID),
		),
	)
	defer span.End()

	// Apply a tight timeout so audit never stalls traffic.
	auditCtx, cancel := context.WithTimeout(ctx, 1*time.Second)
	defer cancel()

	envelope := map[string]any{
		"event_type": "proxy.hit",
		"tenant_id":  event.TenantID,
		"payload":    event,
	}

	body, err := json.Marshal(envelope)
	if err != nil {
		// Should never happen with this struct.
		return fmt.Errorf("audit: marshal HitEvent: %w", err)
	}

	req, err := http.NewRequestWithContext(
		auditCtx,
		http.MethodPost,
		e.adminAPIURL+"/v1/internal/audit/emit",
		bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("audit: create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", e.serviceToken)

	resp, err := e.httpClient.Do(req)
	if err != nil {
		slog.WarnContext(ctx, "audit: emit failed", "error", err)
		return fmt.Errorf("audit: emit request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		slog.WarnContext(ctx, "audit: emit non-2xx response", "status", resp.StatusCode)
		return fmt.Errorf("audit: emit returned status %d", resp.StatusCode)
	}

	return nil
}

// EmitTokenExchanged sends a token.exchanged audit event to admin-api.
//
// This method MUST be called after every token exchange attempt (success or
// failure). The event contains only the hostname portion of the token_url —
// never the full path, query parameters, credential_fields values, or the
// exchanged token value.
//
// Like EmitHit, this is fire-and-forget: errors are logged as warnings and
// do NOT block the proxied request.
//
// Source: Requirements 22.1, 22.2, 22.3, 22.7; design.md §Audit Event.
func (e *Emitter) EmitTokenExchanged(ctx context.Context, event TokenExchangedEvent) error {
	// Start OTel span for the token exchange audit emission.
	tracer := otel.GetTracerProvider().Tracer(tracerName)
	ctx, span := tracer.Start(ctx, "mintkey.proxy.audit.token_exchanged",
		trace.WithSpanKind(trace.SpanKindInternal),
		trace.WithAttributes(
			attribute.String("agent_id", event.AgentID),
			attribute.String("service_id", event.ServiceID),
			attribute.String("tenant_id", event.TenantID),
			attribute.Bool("success", event.Success),
		),
	)
	defer span.End()

	// Apply a tight timeout so audit never stalls traffic.
	auditCtx, cancel := context.WithTimeout(ctx, 1*time.Second)
	defer cancel()

	envelope := map[string]any{
		"event_type": "token.exchanged",
		"tenant_id":  event.TenantID,
		"payload":    event,
	}

	body, err := json.Marshal(envelope)
	if err != nil {
		return fmt.Errorf("audit: marshal TokenExchangedEvent: %w", err)
	}

	req, err := http.NewRequestWithContext(
		auditCtx,
		http.MethodPost,
		e.adminAPIURL+"/v1/internal/audit/emit",
		bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("audit: create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Mintkey-Service-Token", e.serviceToken)

	resp, err := e.httpClient.Do(req)
	if err != nil {
		slog.WarnContext(ctx, "audit: token.exchanged emit failed", "error", err)
		return fmt.Errorf("audit: emit request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		slog.WarnContext(ctx, "audit: token.exchanged emit non-2xx response", "status", resp.StatusCode)
		return fmt.Errorf("audit: emit returned status %d", resp.StatusCode)
	}

	return nil
}

// ExtractHost extracts only the hostname from a URL string.
// Returns the host (including port if present) with no path, query, or
// credentials. Returns an empty string if the URL cannot be parsed.
//
// This is used to redact token_url to host-only for audit events
// (Requirement 22.1: token_url redacted to host only).
func ExtractHost(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil {
		return ""
	}
	return u.Hostname()
}
