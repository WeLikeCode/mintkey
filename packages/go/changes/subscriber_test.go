package changes_test

import (
	"context"
	"testing"
	"time"

	"github.com/mintkey/mintkey/packages/go/changes"
)

// TestClient_PanicsWithoutTenantScope asserts that Start() panics with the
// exact message required by ADR-0014.1 when WithTenantScope is not called.
func TestClient_PanicsWithoutTenantScope(t *testing.T) {
	c := changes.NewClient(nil)

	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected panic, got none")
		}
		msg, ok := r.(string)
		if !ok {
			t.Fatalf("panic value is not a string: %v", r)
		}
		want := "changes: WithTenantScope is required (ADR-0014.1)"
		if msg != want {
			t.Errorf("panic message = %q, want %q", msg, want)
		}
	}()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	c.Start(ctx)
}

// TestClient_NoPanicWithAllTenants asserts that AllTenants sentinel prevents
// the panic and that Start returns cleanly when context is cancelled.
func TestClient_NoPanicWithAllTenants(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately so Start() exits without blocking

	c := changes.NewClient(nil, changes.WithTenantScope(changes.AllTenants))

	// Must not panic.
	c.Start(ctx)
}

// TestClient_NoPanicWithSpecificTenant asserts that a non-empty tenant-ID list
// prevents the panic.
func TestClient_NoPanicWithSpecificTenant(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	scope := changes.NewSpecificTenantsScope([]string{"tenant_01JVQP0000000000000000000A"})
	c := changes.NewClient(nil, changes.WithTenantScope(scope))
	c.Start(ctx)
}

// TestClient_HeartbeatTimeout_TriggersReconnect asserts that when the last
// activity timestamp is 61 seconds in the past the heartbeat checker fires the
// reconnect hook.
func TestClient_HeartbeatTimeout_TriggersReconnect(t *testing.T) {
	reconnected := make(chan struct{}, 1)
	hook := func() { reconnected <- struct{}{} }

	c := changes.NewClient(
		nil,
		changes.WithTenantScope(changes.AllTenants),
		changes.WithReconnectHook(hook),
		// Inject a last-activity time 61 s in the past.
		changes.WithLastActivityOverride(time.Now().Add(-61*time.Second)),
		// Use a very short heartbeat interval so the test doesn't wait 60 s.
		changes.WithHeartbeatInterval(50*time.Millisecond),
	)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	go c.Start(ctx)

	select {
	case <-reconnected:
		// pass
	case <-ctx.Done():
		t.Fatal("reconnect hook was not called within timeout")
	}
}

// TestClient_TenantFilter_FiltersOtherTenants asserts that an event whose
// payload.tenant_id does not match the configured scope is not delivered to the
// event handler.
func TestClient_TenantFilter_FiltersOtherTenants(t *testing.T) {
	const myTenant = "tenant_01JVQP0000000000000000000A"
	const otherTenant = "tenant_01JVQP0000000000000000000B"

	delivered := make(chan string, 4)
	handler := func(channel, payload string) {
		delivered <- payload
	}

	scope := changes.NewSpecificTenantsScope([]string{myTenant})
	c := changes.NewClient(
		nil,
		changes.WithTenantScope(scope),
		changes.WithEventHandler(handler),
	)

	// Inject events directly via the test helper.
	c.InjectEvent("mintkey:service", `{"tenant_id":"`+otherTenant+`","event_type":"service.created","event_id":"change_01"}`)
	c.InjectEvent("mintkey:service", `{"tenant_id":"`+myTenant+`","event_type":"service.created","event_id":"change_02"}`)

	// Give any async delivery a moment.
	time.Sleep(20 * time.Millisecond)

	close(delivered)
	var got []string
	for p := range delivered {
		got = append(got, p)
	}

	if len(got) != 1 {
		t.Fatalf("expected 1 delivered event, got %d: %v", len(got), got)
	}
}
