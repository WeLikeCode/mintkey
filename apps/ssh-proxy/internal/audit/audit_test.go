package audit

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/session"
)

func TestAuditEvent_Serialization(t *testing.T) {
	event := &AuditEvent{
		EventID:    "audit_01HX5J9F8V8H8V0CG3F2Y5J6E1",
		EventType:  "ssh.session.started",
		TenantID:   "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
		ActorID:    "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
		ActorType:  "agent",
		TargetID:   "session_01HX5J9F8V8H8V0CG3F2Y5J6X1",
		TargetType: "ssh_session",
		At:         time.Date(2026, 5, 10, 14, 0, 0, 0, time.UTC),
		Payload: map[string]interface{}{
			"session_id":  "session_01HX5J9F8V8H8V0CG3F2Y5J6X1",
			"agent_id":    "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
			"service_id":  "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
			"source_ip":   "192.168.1.100",
			"auth_method": "jwt",
		},
	}

	// Serialize to JSON
	data, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("failed to marshal event: %v", err)
	}

	// Deserialize back
	var decoded AuditEvent
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal event: %v", err)
	}

	// Verify fields
	if decoded.EventID != event.EventID {
		t.Errorf("EventID = %q, want %q", decoded.EventID, event.EventID)
	}
	if decoded.EventType != event.EventType {
		t.Errorf("EventType = %q, want %q", decoded.EventType, event.EventType)
	}
	if decoded.TenantID != event.TenantID {
		t.Errorf("TenantID = %q, want %q", decoded.TenantID, event.TenantID)
	}
	if decoded.ActorID != event.ActorID {
		t.Errorf("ActorID = %q, want %q", decoded.ActorID, event.ActorID)
	}
	if decoded.TargetType != event.TargetType {
		t.Errorf("TargetType = %q, want %q", decoded.TargetType, event.TargetType)
	}

	// Verify payload
	payload, ok := decoded.Payload["session_id"].(string)
	if !ok {
		t.Error("payload session_id not a string")
	} else if payload != "session_01HX5J9F8V8H8V0CG3F2Y5J6X1" {
		t.Errorf("payload session_id = %q, want session_01HX5J9F8V8H8V0CG3F2Y5J6X1", payload)
	}
}

func TestEmitter_EmitSessionStarted(t *testing.T) {
	// Create emitter with nil queue (will fail, but we're testing the structure)
	emitter := &Emitter{
		queue: nil,
	}

	sessCtx := &session.SessionContext{
		TenantID:   "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
		AgentID:    "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
		ServiceID:  "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
		AuthMethod: "jwt",
	}

	// This will fail because queue is nil, but we're testing the method exists
	err := emitter.EmitSessionStarted(context.Background(), sessCtx, "session_123", "192.168.1.100")
	if err == nil {
		t.Error("EmitSessionStarted() should fail with nil queue")
	}
}

func TestEmitter_EmitSessionExec(t *testing.T) {
	emitter := &Emitter{
		queue: nil,
	}

	sessCtx := &session.SessionContext{
		TenantID:  "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
		AgentID:   "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
		ServiceID: "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
	}

	err := emitter.EmitSessionExec(context.Background(), sessCtx, "session_123", "ls -la", 0)
	if err == nil {
		t.Error("EmitSessionExec() should fail with nil queue")
	}
}

func TestEmitter_EmitSessionSFTP(t *testing.T) {
	emitter := &Emitter{
		queue: nil,
	}

	sessCtx := &session.SessionContext{
		TenantID:  "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
		AgentID:   "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
		ServiceID: "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
	}

	err := emitter.EmitSessionSFTP(context.Background(), sessCtx, "session_123", "read", "/etc/passwd")
	if err == nil {
		t.Error("EmitSessionSFTP() should fail with nil queue")
	}
}

func TestEmitter_EmitSessionEnded(t *testing.T) {
	emitter := &Emitter{
		queue: nil,
	}

	sessCtx := &session.SessionContext{
		TenantID:  "tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9",
		AgentID:   "agent_01HX5J9F8V8H8V0CG3F2Y5J6A1",
		ServiceID: "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
	}

	err := emitter.EmitSessionEnded(context.Background(), sessCtx, "session_123", 3600, 1024, 2048)
	if err == nil {
		t.Error("EmitSessionEnded() should fail with nil queue")
	}
}
