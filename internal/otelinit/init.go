// Package otelinit bootstraps the OpenTelemetry SDK with a mandatory
// SDK-level redaction filter (ADR-0017.6 / S-SEC-1).
//
// The redaction filter is a SpanProcessor that scrubs sensitive span
// attributes before they reach any exporter, ensuring no token, secret,
// password, passphrase, key, or hash value ever leaves the process in an
// OTel span.
package otelinit

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/attribute"
)

// exactForbidden is the set of attribute names that are always redacted.
var exactForbidden = map[string]struct{}{
	"http.request.header.authorization": {},
	"db.statement":                      {},
	"messaging.message.payload":         {},
}

// forbiddenSuffixes are suffix patterns whose matching attributes are redacted.
var forbiddenSuffixes = []string{
	"_token",
	"_secret",
	"_password",
	"_passphrase",
	"_key",
	"_hash",
}

// isSensitive reports whether the attribute key should be redacted.
func isSensitive(key string) bool {
	if _, ok := exactForbidden[key]; ok {
		return true
	}
	for _, suffix := range forbiddenSuffixes {
		if strings.HasSuffix(key, suffix) {
			return true
		}
	}
	return false
}

// RedactAttributes scrubs sensitive attributes from a span attribute map.
// It returns a new map; the input is not modified.
// Exported for testing.
func RedactAttributes(attrs map[string]any) map[string]any {
	out := make(map[string]any, len(attrs))
	for k, v := range attrs {
		if isSensitive(k) {
			out[k] = "[REDACTED]"
		} else {
			out[k] = v
		}
	}
	return out
}

// redactingProcessor wraps a delegate SpanProcessor and redacts sensitive
// span attributes in OnEnd before forwarding to the delegate.
type redactingProcessor struct {
	delegate sdktrace.SpanProcessor
}

// OnStart forwards to the delegate unchanged.
func (r *redactingProcessor) OnStart(parent context.Context, s sdktrace.ReadWriteSpan) {
	r.delegate.OnStart(parent, s)
}

// OnEnd scrubs sensitive attributes then forwards to the delegate.
func (r *redactingProcessor) OnEnd(s sdktrace.ReadOnlySpan) {
	// We can only intercept attribute writes via ReadWriteSpan (OnStart).
	// By OnEnd the span is read-only, so we build a sanitised wrapper and
	// forward it.  The standard approach is to use a wrapping ReadOnlySpan.
	r.delegate.OnEnd(&redactedSpan{ReadOnlySpan: s})
}

// Shutdown delegates shutdown.
func (r *redactingProcessor) Shutdown(ctx context.Context) error {
	return r.delegate.Shutdown(ctx)
}

// ForceFlush delegates force-flush.
func (r *redactingProcessor) ForceFlush(ctx context.Context) error {
	return r.delegate.ForceFlush(ctx)
}

// redactedSpan is a thin ReadOnlySpan wrapper that returns a sanitised
// attribute set from Attributes().
type redactedSpan struct {
	sdktrace.ReadOnlySpan
}

// Attributes returns the span's attributes with sensitive values replaced.
func (rs *redactedSpan) Attributes() []attribute.KeyValue {
	raw := rs.ReadOnlySpan.Attributes()
	out := make([]attribute.KeyValue, len(raw))
	for i, kv := range raw {
		if isSensitive(string(kv.Key)) {
			out[i] = attribute.String(string(kv.Key), "[REDACTED]")
		} else {
			out[i] = kv
		}
	}
	return out
}

// Init bootstraps the OTel SDK with the redaction filter.
// serviceName is e.g. "admin-api", "broker", "vault-adapter".
// otlpEndpoint is the OTel Collector gRPC endpoint, e.g. "otel-collector:4317".
// Returns a shutdown function that flushes and stops the SDK.
//
// OTLP uses async export; a non-reachable endpoint does not cause Init to fail.
func Init(ctx context.Context, serviceName, otlpEndpoint string) (shutdown func(context.Context) error, err error) {
	exp, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(otlpEndpoint),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(serviceName),
		),
	)
	if err != nil {
		return nil, err
	}

	bsp := sdktrace.NewBatchSpanProcessor(exp)
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithSpanProcessor(&redactingProcessor{delegate: bsp}),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)

	return tp.Shutdown, nil
}
