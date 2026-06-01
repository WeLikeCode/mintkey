// Package audit handles audit event emission for SSH sessions.
package audit

import (
	"context"
	"log/slog"
	"time"

	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/packages/go/ulid"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/session"
)

// Emitter emits audit events for SSH sessions.
type Emitter struct {
	queue *auditq.Queue
}

// NewEmitter creates a new audit emitter.
func NewEmitter(queue *auditq.Queue) *Emitter {
	return &Emitter{
		queue: queue,
	}
}

// EmitSessionStarted emits an ssh.session.started event.
func (e *Emitter) EmitSessionStarted(ctx context.Context, sessCtx *session.SessionContext, sessionID, sourceIP string) error {
	return e.emit(ctx, &AuditEvent{
		EventID:    ulid.New("audit_"),
		EventType:  "ssh.session.started",
		TenantID:   sessCtx.TenantID,
		ActorID:    sessCtx.AgentID,
		ActorType:  "agent",
		TargetID:   sessionID,
		TargetType: "ssh_session",
		At:         time.Now().UTC(),
		Payload: map[string]interface{}{
			"session_id":  sessionID,
			"agent_id":    sessCtx.AgentID,
			"service_id":  sessCtx.ServiceID,
			"source_ip":   sourceIP,
			"auth_method": sessCtx.AuthMethod,
		},
	})
}

// EmitSessionExec emits an ssh.session.exec event.
func (e *Emitter) EmitSessionExec(ctx context.Context, sessCtx *session.SessionContext, sessionID, command string, exitCode int) error {
	return e.emit(ctx, &AuditEvent{
		EventID:   ulid.New("audit_"),
		EventType: "ssh.session.exec",
		TenantID:  sessCtx.TenantID,
		ActorID:   sessCtx.AgentID,
		ActorType: "agent",
		TargetID:  sessionID,
		TargetType: "ssh_session",
		At:        time.Now().UTC(),
		Payload: map[string]interface{}{
			"session_id": sessionID,
			"command":    command,
			"exit_code":  exitCode,
		},
	})
}

// EmitSessionSFTP emits an ssh.session.sftp event.
func (e *Emitter) EmitSessionSFTP(ctx context.Context, sessCtx *session.SessionContext, sessionID, operation, path string) error {
	return e.emit(ctx, &AuditEvent{
		EventID:    ulid.New("audit_"),
		EventType:  "ssh.session.sftp",
		TenantID:   sessCtx.TenantID,
		ActorID:    sessCtx.AgentID,
		ActorType:  "agent",
		TargetID:   sessionID,
		TargetType: "ssh_session",
		At:         time.Now().UTC(),
		Payload: map[string]interface{}{
			"session_id": sessionID,
			"operation":  operation,
			"path":       path,
		},
	})
}

// EmitSessionEnded emits an ssh.session.ended event.
func (e *Emitter) EmitSessionEnded(ctx context.Context, sessCtx *session.SessionContext, sessionID string, durationSeconds, bytesSent, bytesReceived int64) error {
	return e.emit(ctx, &AuditEvent{
		EventID:    ulid.New("audit_"),
		EventType:  "ssh.session.ended",
		TenantID:   sessCtx.TenantID,
		ActorID:    sessCtx.AgentID,
		ActorType:  "agent",
		TargetID:   sessionID,
		TargetType: "ssh_session",
		At:         time.Now().UTC(),
		Payload: map[string]interface{}{
			"session_id":       sessionID,
			"duration_seconds": durationSeconds,
			"bytes_sent":       bytesSent,
			"bytes_received":   bytesReceived,
		},
	})
}

func (e *Emitter) emit(_ context.Context, event *AuditEvent) error {
	if e.queue == nil {
		return &emitError{eventType: event.EventType, cause: errNilQueue}
	}

	// Map AuditEvent → auditq.Event. Extra fields (EventID, At) are carried in
	// Payload so they survive the queue's JSON round-trip without schema changes.
	payload := make(map[string]any, len(event.Payload)+2)
	for k, v := range event.Payload {
		payload[k] = v
	}
	payload["event_id"] = event.EventID
	payload["at"] = event.At.Format(time.RFC3339Nano)

	e.queue.Enqueue(auditq.Event{
		EventType:  event.EventType,
		TenantID:   event.TenantID,
		ActorID:    event.ActorID,
		ActorType:  event.ActorType,
		TargetID:   event.TargetID,
		TargetType: event.TargetType,
		Payload:    payload,
	})

	slog.Debug("audit event emitted",
		"event_type", event.EventType,
		"event_id", event.EventID,
		"tenant_id", event.TenantID,
	)

	return nil
}

// emitError wraps an emit failure with the event type.
type emitError struct {
	eventType string
	cause     error
}

func (e *emitError) Error() string {
	return "audit: failed to enqueue " + e.eventType + ": " + e.cause.Error()
}

func (e *emitError) Unwrap() error { return e.cause }

var errNilQueue = errString("audit queue is nil")

type errString string

func (e errString) Error() string { return string(e) }

// AuditEvent represents an SSH audit event. The struct is kept local
// so that callers and tests can construct events without importing auditq.
type AuditEvent struct {
	EventID    string                 `json:"event_id"`
	EventType  string                 `json:"event_type"`
	TenantID   string                 `json:"tenant_id"`
	ActorID    string                 `json:"actor_id"`
	ActorType  string                 `json:"actor_type"`
	TargetID   string                 `json:"target_id"`
	TargetType string                 `json:"target_type"`
	At         time.Time              `json:"at"`
	Payload    map[string]interface{} `json:"payload"`
}
