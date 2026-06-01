// Package trace provides OpenTelemetry tracing for the SSH Proxy.
package trace

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

const (
	// TracerName is the name of the tracer.
	TracerName = "mintkey.ssh-proxy"

	// Span names
	SpanHandleSession    = "mintkey.ssh.handle_session"
	SpanAuthenticate     = "mintkey.ssh.authenticate"
	SpanFetchCredential  = "mintkey.ssh.fetch_credential"
	SpanConnectBackend   = "mintkey.ssh.connect_backend"
	SpanBridgeChannels   = "mintkey.ssh.bridge_channels"

	// Attribute keys
	AttrSessionID            = "mintkey.ssh.session_id"
	AttrSessionDuration      = "mintkey.ssh.session_duration_seconds"
	AttrBytesSent            = "mintkey.ssh.bytes_sent"
	AttrBytesReceived        = "mintkey.ssh.bytes_received"
	AttrAuthMethod           = "mintkey.ssh.auth_method"
	AttrCommandCount         = "mintkey.ssh.command_count"
	AttrSFTPOperationCount   = "mintkey.ssh.sftp_operation_count"
	AttrCommandBlocked       = "mintkey.ssh.command_blocked"
	AttrAgentID              = "mintkey.agent_id"
	AttrServiceID            = "mintkey.service_id"
	AttrTenantID             = "mintkey.tenant_id"
)

// Tracer returns the global tracer for the SSH Proxy.
func Tracer() trace.Tracer {
	return otel.Tracer(TracerName)
}

// StartSpan starts a new span with the given name.
func StartSpan(ctx context.Context, name string, opts ...trace.SpanStartOption) (context.Context, trace.Span) {
	return Tracer().Start(ctx, name, opts...)
}

// StartSessionSpan starts a span for an SSH session.
func StartSessionSpan(ctx context.Context, sessionID, agentID, serviceID, tenantID, authMethod string) (context.Context, trace.Span) {
	return StartSpan(ctx, SpanHandleSession,
		trace.WithAttributes(
			attribute.String(AttrSessionID, sessionID),
			attribute.String(AttrAgentID, agentID),
			attribute.String(AttrServiceID, serviceID),
			attribute.String(AttrTenantID, tenantID),
			attribute.String(AttrAuthMethod, authMethod),
		),
	)
}

// StartAuthSpan starts a span for authentication.
func StartAuthSpan(ctx context.Context, method string) (context.Context, trace.Span) {
	return StartSpan(ctx, SpanAuthenticate,
		trace.WithAttributes(
			attribute.String(AttrAuthMethod, method),
		),
	)
}

// StartFetchCredentialSpan starts a span for fetching credentials from Vault.
func StartFetchCredentialSpan(ctx context.Context, serviceID string) (context.Context, trace.Span) {
	return StartSpan(ctx, SpanFetchCredential,
		trace.WithAttributes(
			attribute.String(AttrServiceID, serviceID),
		),
	)
}

// StartConnectBackendSpan starts a span for connecting to the backend.
func StartConnectBackendSpan(ctx context.Context, targetAddr string) (context.Context, trace.Span) {
	return StartSpan(ctx, SpanConnectBackend,
		trace.WithAttributes(
			attribute.String("mintkey.ssh.target_addr", targetAddr),
		),
	)
}

// StartBridgeChannelsSpan starts a span for bridging channels.
func StartBridgeChannelsSpan(ctx context.Context, sessionID string) (context.Context, trace.Span) {
	return StartSpan(ctx, SpanBridgeChannels,
		trace.WithAttributes(
			attribute.String(AttrSessionID, sessionID),
		),
	)
}

// RecordSessionEnd records session end attributes on a span.
func RecordSessionEnd(span trace.Span, durationSeconds float64, bytesSent, bytesReceived int64, commandCount, sftpOperationCount int, commandBlocked bool) {
	span.SetAttributes(
		attribute.Float64(AttrSessionDuration, durationSeconds),
		attribute.Int64(AttrBytesSent, bytesSent),
		attribute.Int64(AttrBytesReceived, bytesReceived),
		attribute.Int(AttrCommandCount, commandCount),
		attribute.Int(AttrSFTPOperationCount, sftpOperationCount),
		attribute.Bool(AttrCommandBlocked, commandBlocked),
	)
}

// RecordError records an error on a span.
func RecordError(span trace.Span, err error) {
	if err != nil {
		span.RecordError(err)
	}
}
