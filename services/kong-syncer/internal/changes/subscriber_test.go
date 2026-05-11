// Tests for the changes subscriber tenant-scope enforcement.
//
// Source: ADR-0014.1; Req MT-4; T-1.0.6.
package changes_test

import (
	"context"
	"testing"

	"github.com/mintkey/mintkey/services/kong-syncer/internal/changes"
)

// TestSubscriber_PanicsWithoutTenantScope asserts that Start() panics when
// NewClient is called without WithTenantScope. (ADR-0014.1 / Req MT-4)
func TestSubscriber_PanicsWithoutTenantScope(t *testing.T) {
	c := changes.NewClient(nil)

	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected panic, got none")
		}
		msg, ok := r.(string)
		if !ok {
			t.Fatalf("panic value is not string: %T %v", r, r)
		}
		want := "changes: WithTenantScope is required (ADR-0014.1)"
		if msg != want {
			t.Errorf("panic message = %q, want %q", msg, want)
		}
	}()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	c.Start(ctx) // must panic
}

// TestSubscriber_NoPanicWithTenantScope asserts that Start() does NOT panic
// when WithTenantScope(AllTenants) is provided. (ADR-0014.1)
func TestSubscriber_NoPanicWithTenantScope(t *testing.T) {
	c := changes.NewClient(nil, changes.WithTenantScope(changes.AllTenants))

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately so Start returns without blocking

	// Should not panic.
	c.Start(ctx)
}
