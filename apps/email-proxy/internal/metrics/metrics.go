// Package metrics provides Prometheus metrics for the Email Proxy.
//
// All metrics are scoped under the "mintkey_email_proxy_" prefix and auto-
// register against prometheus.DefaultRegisterer via promauto at package init.
// The /metrics HTTP endpoint is served by promhttp.Handler() in server.go and
// picks these up automatically — no explicit registration call needed.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// RequestsTotal counts HTTP requests by endpoint, scope, and status code.
	RequestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "mintkey_email_proxy_requests_total",
		Help: "Total HTTP requests handled by the email proxy, labelled by endpoint, required scope, and HTTP status.",
	}, []string{"endpoint", "scope", "status"})

	// RequestDuration tracks the latency of each endpoint.
	RequestDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "mintkey_email_proxy_request_duration_seconds",
		Help:    "HTTP request latency in seconds, labelled by endpoint.",
		Buckets: prometheus.DefBuckets,
	}, []string{"endpoint"})

	// OAuth2RefreshTotal counts OAuth2 token refresh attempts by provider and outcome.
	// Outcome values: "success", "revoked", "error".
	OAuth2RefreshTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "mintkey_email_proxy_oauth2_refresh_total",
		Help: "Total OAuth2 token refresh attempts by the email proxy, labelled by provider and outcome (success|revoked|error).",
	}, []string{"provider", "outcome"})

	// RateLimitThrottledTotal counts requests rejected by the per-(agent,service) rate limiter.
	RateLimitThrottledTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "mintkey_email_proxy_rate_limit_throttled_total",
		Help: "Total requests throttled by the per-(agent, service) rate limiter.",
	}, []string{"agent", "service"})

	// ActiveConnections tracks the current IMAP pool connection count by provider.
	ActiveConnections = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "mintkey_email_proxy_active_connections",
		Help: "Current number of active IMAP connections held by the pool, labelled by provider.",
	}, []string{"provider"})

	// AuditEventsEmittedTotal counts audit events by event_type.
	AuditEventsEmittedTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "mintkey_email_proxy_audit_events_emitted_total",
		Help: "Total audit events emitted to the auditq backend, labelled by event_type.",
	}, []string{"event_type"})
)

// RecordRequest increments RequestsTotal and observes RequestDuration.
// Call after the handler returns.
func RecordRequest(endpoint, scope, status string, durationSeconds float64) {
	RequestsTotal.WithLabelValues(endpoint, scope, status).Inc()
	RequestDuration.WithLabelValues(endpoint).Observe(durationSeconds)
}

// RecordOAuth2Refresh increments OAuth2RefreshTotal for the given provider and outcome.
// outcome must be one of "success", "revoked", "error".
func RecordOAuth2Refresh(provider, outcome string) {
	OAuth2RefreshTotal.WithLabelValues(provider, outcome).Inc()
}

// RecordRateLimitThrottle increments RateLimitThrottledTotal.
func RecordRateLimitThrottle(agentID, serviceID string) {
	RateLimitThrottledTotal.WithLabelValues(agentID, serviceID).Inc()
}

// RecordActiveConnections sets the ActiveConnections gauge for a provider.
func RecordActiveConnections(provider string, count float64) {
	ActiveConnections.WithLabelValues(provider).Set(count)
}

// RecordAuditEvent increments AuditEventsEmittedTotal for the given event_type.
func RecordAuditEvent(eventType string) {
	AuditEventsEmittedTotal.WithLabelValues(eventType).Inc()
}
