// Package trace provides OpenTelemetry tracing helpers for the Email Proxy.
//
// The 6 span attribute keys (email.service_id, email.message_id, email.mailbox,
// email.provider, email.attachment_count, email.body_size_bytes) are declared in
// the otelinit allowlist (C-1) and are explicitly permitted to bypass the SDK-level
// suffix-redaction filter.
package trace

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const (
	// TracerName is the service name used for all email-proxy spans.
	TracerName = "mintkey.email-proxy"

	// Span operation names.
	SpanListMailboxes       = "mintkey.email.list_mailboxes"
	SpanListMessages        = "mintkey.email.list_messages"
	SpanSendMessage         = "mintkey.email.send_message"
	SpanSearchMessages      = "mintkey.email.search_messages"
	SpanReadMessage         = "mintkey.email.read_message"
	SpanDeleteMessage       = "mintkey.email.delete_message"
	SpanUpdateFlags         = "mintkey.email.update_flags"
	SpanMoveMessage         = "mintkey.email.move_message"
	SpanDownloadAttachment  = "mintkey.email.download_attachment"

	// Attribute keys — in lockstep with otelinit.emailAllowedAttrs (C-1).
	AttrServiceID       = "email.service_id"
	AttrMessageID       = "email.message_id"
	AttrMailbox         = "email.mailbox"
	AttrProvider        = "email.provider"
	AttrAttachmentCount = "email.attachment_count"
	AttrBodySizeBytes   = "email.body_size_bytes"

	// Shared mintkey attributes (same as ssh-proxy).
	AttrAgentID  = "mintkey.agent_id"
	AttrTenantID = "mintkey.tenant_id"
)

// Tracer returns the global OTel tracer for the Email Proxy.
func Tracer() trace.Tracer {
	return otel.Tracer(TracerName)
}

// StartSpan starts a new span with the given operation name.
func StartSpan(ctx context.Context, op string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	return Tracer().Start(ctx, op, trace.WithAttributes(attrs...))
}

// WithEmailSpan starts a named span with the standard email attributes and
// returns a done function that records any error and ends the span.
//
// Typical usage:
//
//	ctx, done := trace.WithEmailSpan(ctx, trace.SpanListMailboxes,
//	    attribute.String(trace.AttrServiceID, serviceID),
//	    attribute.String(trace.AttrMailbox, "INBOX"),
//	)
//	defer done(err)
func WithEmailSpan(ctx context.Context, op string, attrs ...attribute.KeyValue) (context.Context, func(error)) {
	ctx, span := StartSpan(ctx, op, attrs...)
	done := func(err error) {
		if err != nil {
			span.RecordError(err)
			span.SetStatus(codes.Error, err.Error())
		}
		span.End()
	}
	return ctx, done
}

// SetAttrs sets additional attributes on the span extracted from ctx.
// This is a convenience helper for adding attributes discovered after span start.
func SetAttrs(ctx context.Context, attrs ...attribute.KeyValue) {
	span := trace.SpanFromContext(ctx)
	span.SetAttributes(attrs...)
}

// RecordError records err on the span extracted from ctx (no-op if err is nil).
func RecordError(ctx context.Context, err error) {
	if err == nil {
		return
	}
	span := trace.SpanFromContext(ctx)
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
}
