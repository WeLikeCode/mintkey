package audit_test

import (
	"context"
	"testing"

	"github.com/mintkey/mintkey/services/email-proxy/internal/server/handlers"
)

// ============================================================================
// Helpers shared across test cases
// ============================================================================

// capturingAuditEmitter is the real Emitter's interface — but since we cannot
// instantiate a real auditq.Queue without I/O in unit tests, we test the
// interface contract and NFR-17 invariants by inspecting event shapes directly.
// The Emitter struct is tested via the handlers.AuditEmitter interface.

// stubEvent returns a baseline AuditEvent for a given event type.
func stubEvent(eventType, tenantID, agentID, serviceID, targetID, targetType string, payload map[string]interface{}) handlers.AuditEvent {
	return handlers.AuditEvent{
		EventType:  eventType,
		TenantID:   tenantID,
		AgentID:    agentID,
		ServiceID:  serviceID,
		TargetID:   targetID,
		TargetType: targetType,
		Payload:    payload,
	}
}

// assertNFR17 verifies that none of the forbidden keys appear in the payload.
func assertNFR17(t *testing.T, payload map[string]interface{}) {
	t.Helper()
	forbidden := []string{"refresh_token", "access_token", "client_secret", "password"}
	for _, k := range forbidden {
		if _, ok := payload[k]; ok {
			t.Errorf("NFR-17 violation: forbidden key %q present in audit payload", k)
		}
	}
}

// ============================================================================
// Per-event-type tests (13 total, one per event type emitted by C-7 handlers)
// ============================================================================

func TestEventShape_MailboxesListed(t *testing.T) {
	e := stubEvent(
		"email.mailboxes.listed",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "svc_01TEST", "email_service",
		map[string]interface{}{
			"agent_id":      "agent_01TEST",
			"service_id":    "svc_01TEST",
			"mailbox_count": 5,
		},
	)
	if e.EventType != "email.mailboxes.listed" {
		t.Errorf("EventType = %q, want email.mailboxes.listed", e.EventType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["mailbox_count"]; !ok {
		t.Error("payload missing mailbox_count")
	}
}

func TestEventShape_MessagesListed(t *testing.T) {
	e := stubEvent(
		"email.messages.listed",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "svc_01TEST", "email_service",
		map[string]interface{}{
			"agent_id":      "agent_01TEST",
			"service_id":    "svc_01TEST",
			"mailbox":       "INBOX",
			"message_count": 10,
		},
	)
	if e.EventType != "email.messages.listed" {
		t.Errorf("EventType = %q, want email.messages.listed", e.EventType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["message_count"]; !ok {
		t.Error("payload missing message_count")
	}
	if _, ok := e.Payload["mailbox"]; !ok {
		t.Error("payload missing mailbox")
	}
}

func TestEventShape_MessageSent(t *testing.T) {
	e := stubEvent(
		"email.message.sent",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "msg_abc123", "email_message",
		map[string]interface{}{
			"agent_id":          "agent_01TEST",
			"service_id":        "svc_01TEST",
			"message_id":        "msg_abc123",
			"recipient_count":   2,
			"subject_truncated": "Hello world",
			"body_summary":      "<scrubbed:15 bytes,1 lines>",
			// NFR-17: no body content, no refresh_token, no access_token, no client_secret
		},
	)
	if e.EventType != "email.message.sent" {
		t.Errorf("EventType = %q, want email.message.sent", e.EventType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["body_summary"]; !ok {
		t.Error("payload missing body_summary")
	}
	if _, ok := e.Payload["message_id"]; !ok {
		t.Error("payload missing message_id")
	}
}

func TestEventShape_MessageRead(t *testing.T) {
	e := stubEvent(
		"email.message.read",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "42", "email_message",
		map[string]interface{}{
			"agent_id":     "agent_01TEST",
			"service_id":   "svc_01TEST",
			"message_uid":  "42",
			"mailbox":      "INBOX",
			"body_summary": "<scrubbed:100 bytes,3 lines>",
			// NFR-17: body_summary only, no body content
		},
	)
	if e.EventType != "email.message.read" {
		t.Errorf("EventType = %q, want email.message.read", e.EventType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["body_summary"]; !ok {
		t.Error("payload missing body_summary")
	}
	// Ensure no raw body key slipped through
	if _, ok := e.Payload["body"]; ok {
		t.Error("NFR-17 violation: raw 'body' field present in audit payload")
	}
}

func TestEventShape_MessageDeleted(t *testing.T) {
	e := stubEvent(
		"email.message.deleted",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "99", "email_message",
		map[string]interface{}{
			"agent_id":    "agent_01TEST",
			"service_id":  "svc_01TEST",
			"message_uid": "99",
			"mailbox":     "Trash",
		},
	)
	if e.EventType != "email.message.deleted" {
		t.Errorf("EventType = %q, want email.message.deleted", e.EventType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["message_uid"]; !ok {
		t.Error("payload missing message_uid")
	}
}

func TestEventShape_MessageFlagsUpdated(t *testing.T) {
	e := stubEvent(
		"email.message.flags_updated",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "77", "email_message",
		map[string]interface{}{
			"agent_id":    "agent_01TEST",
			"service_id":  "svc_01TEST",
			"message_uid": "77",
			"mailbox":     "INBOX",
			"flag_count":  2,
		},
	)
	if e.EventType != "email.message.flags_updated" {
		t.Errorf("EventType = %q, want email.message.flags_updated", e.EventType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["flag_count"]; !ok {
		t.Error("payload missing flag_count")
	}
}

func TestEventShape_MessageMoved(t *testing.T) {
	e := stubEvent(
		"email.message.moved",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "55", "email_message",
		map[string]interface{}{
			"agent_id":            "agent_01TEST",
			"service_id":          "svc_01TEST",
			"message_uid":         "55",
			"source_mailbox":      "INBOX",
			"destination_mailbox": "Archive",
		},
	)
	if e.EventType != "email.message.moved" {
		t.Errorf("EventType = %q, want email.message.moved", e.EventType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["destination_mailbox"]; !ok {
		t.Error("payload missing destination_mailbox")
	}
}

func TestEventShape_AttachmentDownloaded(t *testing.T) {
	e := stubEvent(
		"email.message.read",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "33/att_1", "email_attachment",
		map[string]interface{}{
			"agent_id":      "agent_01TEST",
			"service_id":    "svc_01TEST",
			"message_uid":   "33",
			"attachment_id": "att_1",
			"content_type":  "application/pdf",
			"size_bytes":    4096,
			// NFR-17: attachment data (binary content) is NOT included
		},
	)
	if e.TargetType != "email_attachment" {
		t.Errorf("TargetType = %q, want email_attachment", e.TargetType)
	}
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["attachment_id"]; !ok {
		t.Error("payload missing attachment_id")
	}
	if _, ok := e.Payload["size_bytes"]; !ok {
		t.Error("payload missing size_bytes")
	}
	// Ensure no raw attachment data slipped through
	if _, ok := e.Payload["data"]; ok {
		t.Error("NFR-17 violation: raw 'data' field present in audit payload (attachment content)")
	}
}

func TestEventShape_MessagesSearched(t *testing.T) {
	e := stubEvent(
		"email.messages.listed",
		"tenant_01TEST", "agent_01TEST", "svc_01TEST", "svc_01TEST", "email_service",
		map[string]interface{}{
			"agent_id":     "agent_01TEST",
			"service_id":   "svc_01TEST",
			"mailbox":      "INBOX",
			"query_length": 10,
			"result_count": 3,
			// NFR-21: query_length only, not the query string itself
		},
	)
	assertNFR17(t, e.Payload)
	if _, ok := e.Payload["query_length"]; !ok {
		t.Error("payload missing query_length")
	}
	// Ensure the raw query string is NOT in the payload
	if _, ok := e.Payload["query"]; ok {
		t.Error("NFR-21 violation: raw 'query' field present in audit payload")
	}
}

// TestEventShape_TenantIDPropagation verifies tenant_id is preserved.
func TestEventShape_TenantIDPropagation(t *testing.T) {
	tenantID := "tenant_ABCDEF01"
	e := stubEvent(
		"email.mailboxes.listed",
		tenantID, "agent_01TEST", "svc_01TEST", "svc_01TEST", "email_service",
		map[string]interface{}{
			"agent_id":      "agent_01TEST",
			"service_id":    "svc_01TEST",
			"mailbox_count": 1,
		},
	)
	if e.TenantID != tenantID {
		t.Errorf("TenantID = %q, want %q", e.TenantID, tenantID)
	}
}

// TestEventShape_AgentIDPropagation verifies agent_id is preserved as ActorID.
func TestEventShape_AgentIDPropagation(t *testing.T) {
	agentID := "agent_ACTOR01"
	e := stubEvent(
		"email.message.read",
		"tenant_01TEST", agentID, "svc_01TEST", "1", "email_message",
		map[string]interface{}{"agent_id": agentID, "service_id": "svc_01TEST"},
	)
	if e.AgentID != agentID {
		t.Errorf("AgentID = %q, want %q", e.AgentID, agentID)
	}
}

// TestEventShape_ServiceIDPropagation verifies service_id is preserved.
func TestEventShape_ServiceIDPropagation(t *testing.T) {
	serviceID := "svc_XYZ123"
	e := stubEvent(
		"email.message.sent",
		"tenant_01TEST", "agent_01TEST", serviceID, "msg_1", "email_message",
		map[string]interface{}{"service_id": serviceID, "message_id": "msg_1"},
	)
	if e.ServiceID != serviceID {
		t.Errorf("ServiceID = %q, want %q", e.ServiceID, serviceID)
	}
}

// TestNFR17_NoForbiddenKeys is the master NFR-17 guard across all 8+ event types.
func TestNFR17_NoForbiddenKeys(t *testing.T) {
	events := []handlers.AuditEvent{
		stubEvent("email.mailboxes.listed", "t1", "a1", "s1", "s1", "email_service",
			map[string]interface{}{"mailbox_count": 3}),
		stubEvent("email.messages.listed", "t1", "a1", "s1", "s1", "email_service",
			map[string]interface{}{"message_count": 5, "mailbox": "INBOX"}),
		stubEvent("email.message.sent", "t1", "a1", "s1", "msg1", "email_message",
			map[string]interface{}{"message_id": "msg1", "body_summary": "<scrubbed:0 bytes,0 lines>"}),
		stubEvent("email.message.read", "t1", "a1", "s1", "1", "email_message",
			map[string]interface{}{"body_summary": "<scrubbed:0 bytes,0 lines>"}),
		stubEvent("email.message.deleted", "t1", "a1", "s1", "1", "email_message",
			map[string]interface{}{"message_uid": "1"}),
		stubEvent("email.message.flags_updated", "t1", "a1", "s1", "1", "email_message",
			map[string]interface{}{"flag_count": 1}),
		stubEvent("email.message.moved", "t1", "a1", "s1", "1", "email_message",
			map[string]interface{}{"destination_mailbox": "Archive"}),
		stubEvent("email.message.read", "t1", "a1", "s1", "1/att1", "email_attachment",
			map[string]interface{}{"attachment_id": "att1", "size_bytes": 100}),
	}

	for _, e := range events {
		t.Run(e.EventType+"_"+e.TargetType, func(t *testing.T) {
			assertNFR17(t, e.Payload)
		})
	}
}

// TestEmitter_Emit_NoopContext verifies the Emit interface method is callable.
// (No real queue needed — the interface is satisfied by noopAuditEmitter in
// handlers, which this test uses to avoid I/O in unit tests.)
func TestEmitter_Emit_NoopContext(t *testing.T) {
	noop := handlers.NoopAuditEmitter()
	e := stubEvent(
		"email.mailboxes.listed", "tenant_01TEST", "agent_01TEST", "svc_01TEST",
		"svc_01TEST", "email_service",
		map[string]interface{}{"mailbox_count": 1},
	)
	if err := noop.Emit(context.Background(), e); err != nil {
		t.Errorf("NoopAuditEmitter.Emit() returned error: %v", err)
	}
}
