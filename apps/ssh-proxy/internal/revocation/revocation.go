// Package revocation handles agent revocation for the SSH Proxy.
package revocation

import (
	"context"
	"log/slog"
	"sync"

	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/session"
	"github.com/WeLikeCode/mintkey/internal/changes"
)

// Handler handles agent revocation events and terminates active sessions.
type Handler struct {
	sessionMgr *session.Manager
	subscriber *changes.Subscriber
	mu         sync.Mutex
	running    bool
	stopCh     chan struct{}
}

// NewHandler creates a new revocation handler.
func NewHandler(sessionMgr *session.Manager, dbURL string) (*Handler, error) {
	subscriber, err := changes.NewSubscriber(dbURL, "mintkey:agent")
	if err != nil {
		return nil, err
	}

	return &Handler{
		sessionMgr: sessionMgr,
		subscriber: subscriber,
		stopCh:     make(chan struct{}),
	}, nil
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

	go h.listen(ctx)

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
	h.subscriber.Close()
	h.running = false

	slog.Info("revocation handler stopped")
}

func (h *Handler) listen(ctx context.Context) {
	for {
		select {
		case <-h.stopCh:
			return
		case <-ctx.Done():
			return
		default:
			event, err := h.subscriber.Next()
			if err != nil {
				slog.Error("failed to receive revocation event", "error", err)
				continue
			}

			h.handleEvent(ctx, event)
		}
	}
}

func (h *Handler) handleEvent(ctx context.Context, event *changes.Event) {
	if event.EventType != "agent.revoked" {
		return
	}

	agentID := event.TargetID
	slog.Info("agent revoked, terminating sessions", "agent_id", agentID)

	// Terminate all sessions for the revoked agent
	h.sessionMgr.TerminateAgentSessions(agentID)

	slog.Info("terminated sessions for revoked agent", "agent_id", agentID)
}
