// Package metrics provides Prometheus metrics for the SSH Proxy.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// ActiveSessions tracks the number of active SSH sessions.
	ActiveSessions = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "ssh_proxy_active_sessions",
		Help: "Number of active SSH sessions",
	})

	// SessionDuration tracks the duration of SSH sessions.
	SessionDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "ssh_proxy_session_duration_seconds",
		Help:    "Duration of SSH sessions in seconds",
		Buckets: prometheus.ExponentialBuckets(1, 2, 15), // 1s to ~16 hours
	})

	// BytesSent tracks the total bytes sent from agent to backend.
	BytesSent = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ssh_proxy_bytes_sent_total",
		Help: "Total bytes sent from agent to backend",
	})

	// BytesReceived tracks the total bytes received from backend to agent.
	BytesReceived = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ssh_proxy_bytes_received_total",
		Help: "Total bytes received from backend to agent",
	})

	// AuthFailures tracks authentication failures.
	AuthFailures = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "ssh_proxy_auth_failures_total",
		Help: "Total authentication failures",
	}, []string{"method"})

	// CommandBlocks tracks blocked commands.
	CommandBlocks = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ssh_proxy_command_blocks_total",
		Help: "Total commands blocked by filter",
	})

	// SessionTimeouts tracks session timeouts.
	SessionTimeouts = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ssh_proxy_session_timeouts_total",
		Help: "Total session timeouts",
	})

	// BackendConnectionErrors tracks backend connection errors.
	BackendConnectionErrors = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "ssh_proxy_backend_connection_errors_total",
		Help: "Total backend connection errors",
	}, []string{"error_type"})

	// VaultFetchDuration tracks the duration of Vault credential fetches.
	VaultFetchDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "ssh_proxy_vault_fetch_duration_seconds",
		Help:    "Duration of Vault credential fetch operations",
		Buckets: prometheus.DefBuckets,
	})

	// SessionsByAgent tracks sessions per agent.
	SessionsByAgent = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "ssh_proxy_sessions_by_agent",
		Help: "Number of active sessions per agent",
	}, []string{"agent_id"})

	// SessionsByService tracks sessions per service.
	SessionsByService = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "ssh_proxy_sessions_by_service",
		Help: "Number of active sessions per service",
	}, []string{"service_id"})

	// CommandCount tracks the number of commands executed.
	CommandCount = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ssh_proxy_commands_total",
		Help: "Total commands executed",
	})

	// SFTPOperationCount tracks SFTP operations.
	SFTPOperationCount = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "ssh_proxy_sftp_operations_total",
		Help: "Total SFTP operations",
	}, []string{"operation"})
)

// RecordSessionStart records the start of a session.
func RecordSessionStart(agentID, serviceID string) {
	ActiveSessions.Inc()
	SessionsByAgent.WithLabelValues(agentID).Inc()
	SessionsByService.WithLabelValues(serviceID).Inc()
}

// RecordSessionEnd records the end of a session.
func RecordSessionEnd(agentID, serviceID string, durationSeconds float64, bytesSent, bytesReceived int64) {
	ActiveSessions.Dec()
	SessionsByAgent.WithLabelValues(agentID).Dec()
	SessionsByService.WithLabelValues(serviceID).Dec()
	SessionDuration.Observe(durationSeconds)
	BytesSent.Add(float64(bytesSent))
	BytesReceived.Add(float64(bytesReceived))
}

// RecordAuthFailure records an authentication failure.
func RecordAuthFailure(method string) {
	AuthFailures.WithLabelValues(method).Inc()
}

// RecordCommandBlock records a blocked command.
func RecordCommandBlock() {
	CommandBlocks.Inc()
}

// RecordSessionTimeout records a session timeout.
func RecordSessionTimeout() {
	SessionTimeouts.Inc()
}

// RecordBackendConnectionError records a backend connection error.
func RecordBackendConnectionError(errorType string) {
	BackendConnectionErrors.WithLabelValues(errorType).Inc()
}

// RecordVaultFetch records a Vault fetch operation.
func RecordVaultFetch(durationSeconds float64) {
	VaultFetchDuration.Observe(durationSeconds)
}

// RecordCommand records a command execution.
func RecordCommand() {
	CommandCount.Inc()
}

// RecordSFTPOperation records an SFTP operation.
func RecordSFTPOperation(operation string) {
	SFTPOperationCount.WithLabelValues(operation).Inc()
}
