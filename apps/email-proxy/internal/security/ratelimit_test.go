package security_test

import (
	"context"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
)

// ---------------------------------------------------------------------------
// Rate limiter tests (in-memory sliding-window)
// ---------------------------------------------------------------------------

func TestRateLimit_UnderLimit(t *testing.T) {
	rl := security.NewRateLimiter()
	ctx := context.Background()
	for i := 0; i < 5; i++ {
		if err := rl.Allow(ctx, "agent-1", "svc-1", 10); err != nil {
			t.Fatalf("call %d should be allowed: %v", i, err)
		}
	}
}

func TestRateLimit_AtLimitThrottled(t *testing.T) {
	rl := security.NewRateLimiter()
	ctx := context.Background()
	limit := 3
	for i := 0; i < limit; i++ {
		if err := rl.Allow(ctx, "agent-2", "svc-2", limit); err != nil {
			t.Fatalf("call %d should be allowed: %v", i, err)
		}
	}
	if err := rl.Allow(ctx, "agent-2", "svc-2", limit); err == nil {
		t.Error("call at limit+1 should be throttled")
	}
}

func TestRateLimit_IsolatedByAgentAndService(t *testing.T) {
	rl := security.NewRateLimiter()
	ctx := context.Background()
	// Exhaust limit for agent-3 / svc-3
	for i := 0; i < 2; i++ {
		_ = rl.Allow(ctx, "agent-3", "svc-3", 2)
	}
	// Different service should not be affected
	if err := rl.Allow(ctx, "agent-3", "svc-other", 2); err != nil {
		t.Errorf("different service should have independent counter: %v", err)
	}
	// Different agent should not be affected
	if err := rl.Allow(ctx, "agent-other", "svc-3", 2); err != nil {
		t.Errorf("different agent should have independent counter: %v", err)
	}
}

func TestRateLimit_WindowSlide(t *testing.T) {
	rl := security.NewRateLimiterWithClock(func() time.Time {
		// Fixed time at start
		return time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	})
	ctx := context.Background()
	// Exhaust limit
	for i := 0; i < 2; i++ {
		_ = rl.Allow(ctx, "agent-win", "svc-win", 2)
	}
	if err := rl.Allow(ctx, "agent-win", "svc-win", 2); err == nil {
		t.Fatal("should be throttled before window slides")
	}
	// Advance clock > 60 seconds
	rl.SetClock(func() time.Time {
		return time.Date(2026, 1, 1, 0, 1, 1, 0, time.UTC)
	})
	if err := rl.Allow(ctx, "agent-win", "svc-win", 2); err != nil {
		t.Errorf("after window slide, call should be allowed: %v", err)
	}
}

func TestRateLimit_ZeroLimit(t *testing.T) {
	rl := security.NewRateLimiter()
	ctx := context.Background()
	// limitPerMin=0 means everything is throttled
	if err := rl.Allow(ctx, "agent-z", "svc-z", 0); err == nil {
		t.Error("zero limit should throttle all calls")
	}
}
