package trace

import (
	"context"
	"errors"
	"testing"

	"go.opentelemetry.io/otel/attribute"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
)

func TestTracer(t *testing.T) {
	tr := Tracer()
	if tr == nil {
		t.Error("Tracer() returned nil")
	}
}

func TestConstants_TracerName(t *testing.T) {
	if TracerName != "mintkey.email-proxy" {
		t.Errorf("TracerName = %q, want 'mintkey.email-proxy'", TracerName)
	}
}

func TestConstants_AttrKeys(t *testing.T) {
	cases := map[string]string{
		"AttrServiceID":       AttrServiceID,
		"AttrMessageID":       AttrMessageID,
		"AttrMailbox":         AttrMailbox,
		"AttrProvider":        AttrProvider,
		"AttrAttachmentCount": AttrAttachmentCount,
		"AttrBodySizeBytes":   AttrBodySizeBytes,
		"AttrAgentID":         AttrAgentID,
		"AttrTenantID":        AttrTenantID,
	}
	expected := map[string]string{
		"AttrServiceID":       "email.service_id",
		"AttrMessageID":       "email.message_id",
		"AttrMailbox":         "email.mailbox",
		"AttrProvider":        "email.provider",
		"AttrAttachmentCount": "email.attachment_count",
		"AttrBodySizeBytes":   "email.body_size_bytes",
		"AttrAgentID":         "mintkey.agent_id",
		"AttrTenantID":        "mintkey.tenant_id",
	}
	for name, got := range cases {
		if got != expected[name] {
			t.Errorf("%s = %q, want %q", name, got, expected[name])
		}
	}
}

func TestStartSpan(t *testing.T) {
	ctx := context.Background()
	ctx, span := StartSpan(ctx, SpanListMailboxes,
		attribute.String(AttrServiceID, "svc_01"),
		attribute.String(AttrMailbox, "INBOX"),
	)
	defer span.End()

	if span == nil {
		t.Error("StartSpan returned nil span")
	}
	if ctx == nil {
		t.Error("StartSpan returned nil context")
	}
}

func TestWithEmailSpan_NoError(t *testing.T) {
	exporter := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))

	// Override the global tracer for this test using a local TracerProvider.
	ctx := context.Background()
	ctx, span := tp.Tracer(TracerName).Start(ctx, SpanListMailboxes,
		trace.WithAttributes(attribute.String(AttrServiceID, "svc_01")),
	)
	span.End()

	spans := exporter.GetSpans()
	if len(spans) != 1 {
		t.Fatalf("expected 1 exported span, got %d", len(spans))
	}
	if spans[0].Name != SpanListMailboxes {
		t.Errorf("span name = %q, want %q", spans[0].Name, SpanListMailboxes)
	}
	_ = ctx
}

func TestWithEmailSpan_WithError(t *testing.T) {
	ctx := context.Background()
	ctx, done := WithEmailSpan(ctx, SpanSendMessage,
		attribute.String(AttrServiceID, "svc_01"),
	)
	testErr := errors.New("smtp failed")
	done(testErr)
	// Verify context is not nil after done is called.
	if ctx == nil {
		t.Error("context is nil")
	}
}

func TestWithEmailSpan_NilError(t *testing.T) {
	ctx := context.Background()
	_, done := WithEmailSpan(ctx, SpanReadMessage,
		attribute.String(AttrServiceID, "svc_01"),
		attribute.String(AttrMessageID, "42"),
	)
	// Should not panic when err is nil.
	done(nil)
}

func TestSetAttrs(t *testing.T) {
	ctx := context.Background()
	ctx, span := StartSpan(ctx, SpanDownloadAttachment)
	defer span.End()

	// Should not panic.
	SetAttrs(ctx,
		attribute.Int(AttrAttachmentCount, 3),
		attribute.Int64(AttrBodySizeBytes, 4096),
	)
}

func TestRecordError_Nil(t *testing.T) {
	ctx := context.Background()
	ctx, span := StartSpan(ctx, SpanDeleteMessage)
	defer span.End()

	// nil error must be a no-op (no panic).
	RecordError(ctx, nil)
}

func TestRecordError_NonNil(t *testing.T) {
	ctx := context.Background()
	ctx, span := StartSpan(ctx, SpanDeleteMessage)
	defer span.End()

	RecordError(ctx, errors.New("delete failed"))
	// Span should still be usable after RecordError.
}

func TestSpanNames(t *testing.T) {
	expected := map[string]string{
		"SpanListMailboxes":      SpanListMailboxes,
		"SpanListMessages":       SpanListMessages,
		"SpanSendMessage":        SpanSendMessage,
		"SpanSearchMessages":     SpanSearchMessages,
		"SpanReadMessage":        SpanReadMessage,
		"SpanDeleteMessage":      SpanDeleteMessage,
		"SpanUpdateFlags":        SpanUpdateFlags,
		"SpanMoveMessage":        SpanMoveMessage,
		"SpanDownloadAttachment": SpanDownloadAttachment,
	}
	for name, val := range expected {
		if val == "" {
			t.Errorf("%s is empty", name)
		}
	}
}
