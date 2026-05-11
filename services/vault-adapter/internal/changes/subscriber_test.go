package changes

import (
	"testing"
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
