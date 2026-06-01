package revocation

import (
	"context"
	"testing"
	"time"

	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/session"
)

func TestNewHandler(t *testing.T) {
	sessionMgr := session.NewManager(5)

	// This will fail because we don't have a real database URL
	// In a real test, we'd use a test database or mock
	handler, err := NewHandler(sessionMgr, "postgres://invalid")
	if err == nil {
		t.Error("NewHandler() should fail with invalid database URL")
	}

	if handler != nil {
		t.Error("NewHandler() should return nil on error")
	}
}

func TestHandler_StartStop(t *testing.T) {
	sessionMgr := session.NewManager(5)

	// Create handler with nil subscriber (will fail, but we're testing the structure)
	handler := &Handler{
		sessionMgr: sessionMgr,
		subscriber: nil,
		stopCh:     make(chan struct{}),
	}

	// Start should handle nil subscriber gracefully
	ctx := context.Background()
	err := handler.Start(ctx)
	if err != nil {
		t.Errorf("Start() error = %v", err)
	}

	// Verify running flag
	if !handler.running {
		t.Error("handler should be running after Start()")
	}

	// Start again (should be idempotent)
	err = handler.Start(ctx)
	if err != nil {
		t.Errorf("second Start() error = %v", err)
	}

	// Stop
	handler.Stop()

	// Verify stopped
	if handler.running {
		t.Error("handler should not be running after Stop()")
	}

	// Stop again (should be idempotent)
	handler.Stop()
}

func TestHandler_HandleEvent(t *testing.T) {
	sessionMgr := session.NewManager(5)

	handler := &Handler{
		sessionMgr: sessionMgr,
	}

	// Test with non-revocation event (should be ignored)
	ctx := context.Background()
	event := &changes.Event{
		EventType: "agent.created",
		TargetID:  "agent_123",
	}

	handler.handleEvent(ctx, event)

	// Verify no panic occurred

	// Test with revocation event
	event = &changes.Event{
		EventType: "agent.revoked",
		TargetID:  "agent_123",
	}

	handler.handleEvent(ctx, event)

	// Verify no panic occurred
}

func TestHandler_Listen_ContextCancellation(t *testing.T) {
	sessionMgr := session.NewManager(5)

	handler := &Handler{
		sessionMgr: sessionMgr,
		subscriber: nil,
		stopCh:     make(chan struct{}),
	}

	ctx, cancel := context.WithCancel(context.Background())

	// Start listening in goroutine
	done := make(chan struct{})
	go func() {
		handler.listen(ctx)
		close(done)
	}()

	// Cancel context
	cancel()

	// Wait for listen to exit
	select {
	case <-done:
		// Success
	case <-time.After(2 * time.Second):
		t.Error("listen() did not exit after context cancellation")
	}
}

func TestHandler_Listen_StopChannel(t *testing.T) {
	sessionMgr := session.NewManager(5)

	handler := &Handler{
		sessionMgr: sessionMgr,
		subscriber: nil,
		stopCh:     make(chan struct{}),
	}

	ctx := context.Background()

	// Start listening in goroutine
	done := make(chan struct{})
	go func() {
		handler.listen(ctx)
		close(done)
	}()

	// Signal stop
	close(handler.stopCh)

	// Wait for listen to exit
	select {
	case <-done:
		// Success
	case <-time.After(2 * time.Second):
		t.Error("listen() did not exit after stop signal")
	}
}
