// Package audit handles audit event emission for SSH sessions.
package audit

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/session"
	"github.com/WeLikeCode/mintkey/internal/auditq"
	"github.com/WeLikeCode/mintkey/internal/ulid"
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
	event := &AuditEvent{
		EventID:    ulid.New("audit"),
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
	}

	return e.emit(ctx, event)
}

// EmitSessionExec emits an ssh.session.exec event.
func (e *Emitter) EmitSessionExec(ctx context.Context, sessCtx *session.SessionContext, sessionID, command string, exitCode int) error {
	event := &AuditEvent{
		EventID:    ulid.New("audit"),
		EventType:  "ssh.session.exec",
		TenantID:   sessCtx.TenantID,
		ActorID:    sessCtx.AgentID,
		ActorType:  "agent",
		TargetID:   sessionID,
		TargetType: "ssh_session",
		At:         time.Now().UTC(),
		Payload: map[string]interface{}{
			"session_id": sessionID,
			"command":    command,
			"exit_code":  exitCode,
		},
	}

	return e.emit(ctx, event)
}

// EmitSessionSFTP emits an ssh.session.sftp event.
func (e *Emitter) EmitSessionSFTP(ctx context.Context, sessCtx *session.SessionContext, sessionID, operation, path string) error {
	event := &AuditEvent{
		EventID:    ulid.New("audit"),
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
	}

	return e.emit(ctx, event)
}

// EmitSessionEnded emits an ssh.session.ended event.
func (e *Emitter) EmitSessionEnded(ctx context.Context, sessCtx *session.SessionContext, sessionID string, durationSeconds, bytesSent, bytesReceived int64) error {
	event := &AuditEvent{
		EventID:    ulid.New("audit"),
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
	}

	return e.emit(ctx, event)
}

func (e *Emitter) emit(ctx context.Context, event *AuditEvent) error {
	// Serialize event to JSON
	data, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal audit event: %w", err)
	}

	// Enqueue event
	if err := e.queue.Enqueue(ctx, event.TenantID, data); err != nil {
		slog.Error("failed to enqueue audit event",
			"event_type", event.EventType,
			"error", err,
		)
		return err
	}

	slog.Debug("audit event emitted",
		"event_type", event.EventType,
		"event_id", event.EventID,
		"tenant_id", event.TenantID,
	)

	return nil
}

// AuditEvent represents an audit event.
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
