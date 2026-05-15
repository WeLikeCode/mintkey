package changes

import (
	"testing"
	"time"
)

// mockCache records calls to InvalidateByService for assertion.
type mockCache struct {
	calls []invalidateCall
}

type invalidateCall struct {
	tenantID  string
	serviceID string
}

func (m *mockCache) InvalidateByService(tenantID, serviceID string) {
	m.calls = append(m.calls, invalidateCall{tenantID: tenantID, serviceID: serviceID})
}

func TestHandleCredentialRotated(t *testing.T) {
	cache := &mockCache{}
	sub := NewSubscriber("", cache)

	payload := `{"event_type":"credential.rotated","tenant_id":"t1","service_id":"s1","key_version":2}`
	if err := sub.handleNotification(payload); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(cache.calls) != 1 {
		t.Fatalf("expected 1 invalidation call, got %d", len(cache.calls))
	}
	got := cache.calls[0]
	if got.tenantID != "t1" {
		t.Errorf("tenantID: got %q, want %q", got.tenantID, "t1")
	}
	if got.serviceID != "s1" {
		t.Errorf("serviceID: got %q, want %q", got.serviceID, "s1")
	}
}

func TestHandleUnknownEventType(t *testing.T) {
	cache := &mockCache{}
	sub := NewSubscriber("", cache)

	payload := `{"event_type":"credential.created","tenant_id":"t1","service_id":"s1","key_version":1}`
	if err := sub.handleNotification(payload); err != nil {
		t.Fatalf("unexpected error for unknown event type: %v", err)
	}

	if len(cache.calls) != 0 {
		t.Fatalf("expected no invalidation calls for unknown event type, got %d", len(cache.calls))
	}
}

func TestHandleMalformedJSON(t *testing.T) {
	cache := &mockCache{}
	sub := NewSubscriber("", cache)

	if err := sub.handleNotification("{not valid json"); err == nil {
		t.Fatal("expected error for malformed JSON, got nil")
	}

	if len(cache.calls) != 0 {
		t.Fatalf("expected no invalidation calls on malformed JSON, got %d", len(cache.calls))
	}
}

// TestLagSeconds_NeverReceived verifies LagSeconds returns 0 when no message
// has been received yet (lastMessageNanos == 0).
func TestLagSeconds_NeverReceived(t *testing.T) {
	sub := NewSubscriber("", &mockCache{})
	lag := sub.LagSeconds()
	if lag != 0 {
		t.Errorf("LagSeconds() before any message: got %v, want 0", lag)
	}
}

// TestLagSeconds_AfterMessage stores a known time and verifies LagSeconds
// returns a non-negative value within a reasonable tolerance.
func TestLagSeconds_AfterMessage(t *testing.T) {
	sub := NewSubscriber("", &mockCache{})

	// Store a timestamp 200 ms in the past.
	past := time.Now().Add(-200 * time.Millisecond).UnixNano()
	sub.lastMessageNanos.Store(past)

	lag := sub.LagSeconds()

	// Should be >= 0.2 seconds (200 ms) and < 5 seconds (generous upper bound
	// for CI environment slowness).
	const lower = 0.2
	const upper = 5.0
	if lag < lower {
		t.Errorf("LagSeconds() = %v, want >= %v", lag, lower)
	}
	if lag > upper {
		t.Errorf("LagSeconds() = %v, want < %v (possible timer issue)", lag, upper)
	}
}

// TestLagSeconds_UpdatedByHandleNotification verifies that handleNotification
// updates lastMessageNanos so LagSeconds reflects a recent timestamp.
func TestLagSeconds_UpdatedByHandleNotification(t *testing.T) {
	mc := &mockCache{}
	sub := NewSubscriber("", mc)

	// Before any notification, lag is 0.
	if sub.LagSeconds() != 0 {
		t.Fatalf("expected lag=0 before any notification")
	}

	payload := `{"event_type":"credential.rotated","tenant_id":"t1","service_id":"s1","key_version":2}`
	if err := sub.handleNotification(payload); err != nil {
		t.Fatalf("handleNotification: %v", err)
	}

	// After notification, lag should be a small positive number.
	lag := sub.LagSeconds()
	if lag < 0 {
		t.Errorf("LagSeconds() after notification: got negative %v", lag)
	}
	// Should have been set within the last second.
	if lag > 1.0 {
		t.Errorf("LagSeconds() after notification: got %v, expected < 1.0s", lag)
	}
}
