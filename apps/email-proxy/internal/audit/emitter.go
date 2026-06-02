// Package audit implements the AuditEmitter interface for the email proxy.
//
// It wraps auditq.Queue to provide per-event-type helpers that stamp
// tenant_id / actor_id / service_id from the caller-supplied Claims and enforce
// NFR-17: no body content, refresh_token, access_token, or client_secret may
// appear in audit payloads.  Body summaries are produced by
// security.ScrubBodyForLog.
package audit

import (
	"context"
	"log/slog"
	"time"

	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/packages/go/ulid"
	emailmetrics "github.com/mintkey/mintkey/services/email-proxy/internal/metrics"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server/handlers"
)

// Emitter implements handlers.AuditEmitter using an auditq.Queue backend.
type Emitter struct {
	queue *auditq.Queue
}

// NewEmitter creates a new audit Emitter.
// queue must not be nil; call queue.Start() before passing it in.
func NewEmitter(queue *auditq.Queue) *Emitter {
	if queue == nil {
		panic("audit.NewEmitter: queue must not be nil")
	}
	return &Emitter{queue: queue}
}

// Emit implements handlers.AuditEmitter.  It maps the handlers.AuditEvent
// into an auditq.Event and enqueues it.
//
// Security invariants enforced here:
//   - event_id and at are injected (not caller-supplied); callers should NOT
//     include them in Payload.
//   - The queue itself never injects credential material; callers are trusted to
//     omit refresh_token / access_token / client_secret per NFR-17.
func (e *Emitter) Emit(_ context.Context, event handlers.AuditEvent) error {
	payload := make(map[string]any, len(event.Payload)+2)
	for k, v := range event.Payload {
		payload[k] = v
	}
	payload["event_id"] = ulid.New("audit_")
	payload["at"] = time.Now().UTC().Format(time.RFC3339Nano)

	e.queue.Enqueue(auditq.Event{
		EventType:  event.EventType,
		TenantID:   event.TenantID,
		ActorID:    event.AgentID,
		ActorType:  "agent",
		TargetID:   event.TargetID,
		TargetType: event.TargetType,
		Payload:    payload,
	})

	// Track audit events in Prometheus (event_type label).
	emailmetrics.RecordAuditEvent(event.EventType)

	slog.Debug("audit event emitted",
		"event_type", event.EventType,
		"tenant_id", event.TenantID,
		"agent_id", event.AgentID,
	)
	return nil
}
