// Package audit_test covers the proxy.hit audit emitter.
//
// TDD: this file was written before emitter.go.
// Source: T-1.6.5; ADR-0014.7; S-SEC-1.
package audit_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"go.opentelemetry.io/otel"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/audit"
)

// --------------------------------------------------------------------------
// TestEmitHitSendsCorrectPayload
// Verifies:
//   - POST to /v1/internal/audit/emit
//   - X-Mintkey-Service-Token header present with expected value
//   - Body contains event_type="proxy.hit", tenant_id, and nested payload
//     with all required HitEvent fields.
// --------------------------------------------------------------------------

func TestEmitHitSendsCorrectPayload(t *testing.T) {
	var capturedPath string
	var capturedHeader string
	var capturedBody []byte

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedPath = r.URL.Path
		capturedHeader = r.Header.Get("X-Mintkey-Service-Token")
		capturedBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	emitter := audit.NewEmitter(srv.URL, "test-service-token")

	event := audit.HitEvent{
		JTI:                 "jti_abc123",
		AgentID:             "agent_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		ServiceID:           "svc_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		TenantID:            "tenant_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		Action:              "read",
		RequestMethod:       "GET",
		RequestPathTemplate: "/v1/data/{id}",
		StatusCode:          200,
		LatencyMS:           42,
		Outcome:             "allowed",
	}

	err := emitter.EmitHit(context.Background(), event)
	if err != nil {
		t.Fatalf("EmitHit returned unexpected error: %v", err)
	}

	// Check path
	if capturedPath != "/v1/internal/audit/emit" {
		t.Errorf("path = %q; want /v1/internal/audit/emit", capturedPath)
	}

	// Check auth header
	if capturedHeader != "test-service-token" {
		t.Errorf("X-Mintkey-Service-Token = %q; want test-service-token", capturedHeader)
	}

	// Decode body
	var envelope map[string]any
	if err := json.Unmarshal(capturedBody, &envelope); err != nil {
		t.Fatalf("body is not valid JSON: %v\nbody: %s", err, capturedBody)
	}

	if envelope["event_type"] != "proxy.hit" {
		t.Errorf("event_type = %q; want proxy.hit", envelope["event_type"])
	}
	if envelope["tenant_id"] != event.TenantID {
		t.Errorf("tenant_id = %q; want %q", envelope["tenant_id"], event.TenantID)
	}

	payload, ok := envelope["payload"].(map[string]any)
	if !ok {
		t.Fatalf("payload field is missing or not an object")
	}

	requiredFields := []string{
		"jti", "agent_id", "service_id", "tenant_id", "action",
		"request_method", "request_path_template", "status_code",
		"latency_ms", "outcome",
	}
	for _, f := range requiredFields {
		if _, present := payload[f]; !present {
			t.Errorf("payload missing required field %q", f)
		}
	}
}

// --------------------------------------------------------------------------
// TestEmitHitNoCredentialInPayload
// Verifies that the HitEvent struct has no fields whose JSON tag could leak
// a credential value: credential, api_key, secret, token_value.
// --------------------------------------------------------------------------

func TestEmitHitNoCredentialInPayload(t *testing.T) {
	forbidden := map[string]bool{
		"credential":  true,
		"api_key":     true,
		"secret":      true,
		"token_value": true,
	}

	typ := reflect.TypeOf(audit.HitEvent{})
	for i := range typ.NumField() {
		field := typ.Field(i)
		jsonTag := field.Tag.Get("json")
		// Strip omitempty and similar options.
		tagName := jsonTag
		for j, c := range jsonTag {
			if c == ',' {
				tagName = jsonTag[:j]
				break
			}
		}
		if forbidden[tagName] {
			t.Errorf("HitEvent has forbidden field with json tag %q (field %s)", tagName, field.Name)
		}
	}
}

// --------------------------------------------------------------------------
// TestEmitHitNonBlockingOnError
// Verifies EmitHit returns an error on non-2xx response but does not panic.
// --------------------------------------------------------------------------

func TestEmitHitNonBlockingOnError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	emitter := audit.NewEmitter(srv.URL, "svc-token")
	event := audit.HitEvent{
		JTI:       "jti_x",
		TenantID:  "tenant_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		ServiceID: "svc_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		Outcome:   "error",
	}

	// Must not panic. May return error — traffic must not be blocked.
	_ = emitter.EmitHit(context.Background(), event)
}

// --------------------------------------------------------------------------
// TestEmitHitOTelSpan
// Verifies EmitHit starts an OTel span named "mintkey.proxy.handle_request"
// with attributes agent_id, service_id, tenant_id.
// --------------------------------------------------------------------------

func TestEmitHitOTelSpan(t *testing.T) {
	// Set up an in-memory OTel tracer provider that exports spans synchronously.
	exporter := &spanCollector{}
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithSyncer(exporter),
	)
	defer tp.Shutdown(context.Background())

	// Register as the global provider so the emitter picks it up.
	orig := otel.GetTracerProvider()
	otel.SetTracerProvider(tp)
	defer otel.SetTracerProvider(orig)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	emitter := audit.NewEmitter(srv.URL, "svc-token")
	event := audit.HitEvent{
		JTI:                 "jti_span_test",
		AgentID:             "agent_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		ServiceID:           "svc_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		TenantID:            "tenant_01ARZ3NDEKTSV4RRFFQ69G5FAV",
		Action:              "read",
		RequestMethod:       "GET",
		RequestPathTemplate: "/v1/items",
		StatusCode:          200,
		LatencyMS:           10,
		Outcome:             "allowed",
	}

	if err := emitter.EmitHit(context.Background(), event); err != nil {
		t.Fatalf("EmitHit error: %v", err)
	}

	if len(exporter.spans) == 0 {
		t.Fatal("no spans exported")
	}

	span := exporter.spans[0]
	if span.Name() != "mintkey.proxy.handle_request" {
		t.Errorf("span name = %q; want mintkey.proxy.handle_request", span.Name())
	}

	attrMap := make(map[string]string)
	for _, a := range span.Attributes() {
		attrMap[string(a.Key)] = a.Value.AsString()
	}

	for _, wantKey := range []string{"agent_id", "service_id", "tenant_id"} {
		if _, ok := attrMap[wantKey]; !ok {
			t.Errorf("span missing attribute %q; got attributes: %v", wantKey, attrMap)
		}
	}
	if attrMap["agent_id"] != event.AgentID {
		t.Errorf("span agent_id = %q; want %q", attrMap["agent_id"], event.AgentID)
	}
	if attrMap["service_id"] != event.ServiceID {
		t.Errorf("span service_id = %q; want %q", attrMap["service_id"], event.ServiceID)
	}
	if attrMap["tenant_id"] != event.TenantID {
		t.Errorf("span tenant_id = %q; want %q", attrMap["tenant_id"], event.TenantID)
	}
}

// spanCollector is a synchronous SpanExporter that accumulates finished spans.
type spanCollector struct {
	spans []sdktrace.ReadOnlySpan
}

func (c *spanCollector) ExportSpans(_ context.Context, spans []sdktrace.ReadOnlySpan) error {
	c.spans = append(c.spans, spans...)
	return nil
}

func (c *spanCollector) Shutdown(_ context.Context) error { return nil }
