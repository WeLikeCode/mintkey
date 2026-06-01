// Package revocation handles agent revocation for the SSH Proxy.
package revocation

import (
	"context"
	"encoding/json"
	"log/slog"
	"sync"

	"github.com/mintkey/mintkey/packages/go/changes"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/session"
)

// Event is the revocation event payload shape that arrives over the changes
// channel. Only the fields consumed by this package are modelled here.
type Event struct {
	EventType string `json:"event_type"`
	TargetID  string `json:"target_id"`
}

// Handler handles agent revocation events and terminates active sessions.
type Handler struct {
	sessionMgr *session.Manager
	subscriber *changes.Client
	mu         sync.Mutex
	running    bool
	stopCh     chan struct{}
}

// NewHandler creates a new revocation handler.
// dbURL is accepted for interface compatibility; the changes.Client does not
// use a direct DB URL (T-1.2.2 will wire the pgx connection).
func NewHandler(sessionMgr *session.Manager, dbURL string) (*Handler, error) {
	if dbURL == "" {
		return nil, errInvalidDBURL
	}

	h := &Handler{
		sessionMgr: sessionMgr,
		stopCh:     make(chan struct{}),
	}

	// Build a changes client that calls our event handler on each notification.
	client := changes.NewClient(nil,
		changes.WithTenantScope(changes.AllTenants),
		changes.WithEventHandler(func(channel, payload string) {
			var ev Event
			if err := json.Unmarshal([]byte(payload), &ev); err != nil {
				slog.Warn("revocation: failed to parse event",
					"channel", channel,
					"error", err,
				)
				return
			}
			h.handleEvent(context.Background(), &ev)
		}),
	)
	h.subscriber = client
	return h, nil
}

// Start starts listening for revocation events.
func (h *Handler) Start(ctx context.Context) error {
	h.mu.Lock()
	if h.running {
		h.mu.Unlock()
		return nil
	}
	h.running = true
	h.mu.Unlock()

	if h.subscriber != nil {
		go h.subscriber.Start(ctx)
	}

	slog.Info("revocation handler started")
	return nil
}

// Stop stops listening for revocation events.
func (h *Handler) Stop() {
	h.mu.Lock()
	defer h.mu.Unlock()

	if !h.running {
		return
	}

	close(h.stopCh)
	h.running = false

	slog.Info("revocation handler stopped")
}

// listen is retained for test compatibility. The real event delivery is
// via changes.Client.WithEventHandler (see NewHandler). This method
// only watches for stop/cancel signals.
func (h *Handler) listen(ctx context.Context) {
	select {
	case <-h.stopCh:
	case <-ctx.Done():
	}
}

func (h *Handler) handleEvent(_ context.Context, event *Event) {
	if event.EventType != "agent.revoked" {
		return
	}

	agentID := event.TargetID
	slog.Info("agent revoked, terminating sessions", "agent_id", agentID)

	// Terminate all sessions for the revoked agent
	h.sessionMgr.TerminateAgentSessions(agentID)

	slog.Info("terminated sessions for revoked agent", "agent_id", agentID)
}

var errInvalidDBURL = errString("revocation: dbURL must not be empty")

type errString string

func (e errString) Error() string { return string(e) }
