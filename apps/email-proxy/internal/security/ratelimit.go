package security

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// RateLimiter is a per-(agentID, serviceID) sliding-window rate limiter.
//
// Implementation: in-memory sliding-window counter with a configurable
// 1-minute window. Thread-safe.
//
// FUTURE: PG-backed counter for cross-instance rate limit (see C-9 DDL).
// When multiple email-proxy replicas run, each instance maintains its own
// counter. A production deployment should replace (or augment) this with a
// Postgres advisory-lock + rate_limit_events table so all replicas share a
// unified count:
//
//	-- C-9 DDL will add:
//	CREATE TABLE rate_limit_events (
//	    agent_id    TEXT NOT NULL,
//	    service_id  TEXT NOT NULL,
//	    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
//	);
//	CREATE INDEX ON rate_limit_events(agent_id, service_id, ts);
//
//	-- Query pattern:
//	SELECT COUNT(*) FROM rate_limit_events
//	WHERE agent_id = $1 AND service_id = $2
//	  AND ts > NOW() - INTERVAL '1 minute';
//
//	-- And pg_try_advisory_lock_shared using:
//	hashtext('email_rate_limit:' || agent_id || ':' || service_id)
//
// NOTE (R-6 from plan): to avoid hashtext collisions with future rate limiters
// consider using hashtextextended with a dedicated namespace constant.
type RateLimiter struct {
	mu      sync.Mutex
	windows map[string][]time.Time
	clock   func() time.Time
}

// NewRateLimiter returns a RateLimiter using the real wall clock.
func NewRateLimiter() *RateLimiter {
	return &RateLimiter{
		windows: make(map[string][]time.Time),
		clock:   time.Now,
	}
}

// NewRateLimiterWithClock returns a RateLimiter using a custom clock function.
// Intended for testing.
func NewRateLimiterWithClock(clock func() time.Time) *RateLimiter {
	return &RateLimiter{
		windows: make(map[string][]time.Time),
		clock:   clock,
	}
}

// SetClock replaces the clock function on an existing RateLimiter.
// Intended for testing to advance time without creating a new instance.
func (r *RateLimiter) SetClock(clock func() time.Time) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.clock = clock
}

// Allow records a call attempt for (agentID, serviceID) and returns nil if
// the call is within the limitPerMin window, or an error if throttled.
//
// limitPerMin == 0 means deny all.
func (r *RateLimiter) Allow(_ context.Context, agentID, serviceID string, limitPerMin int) error {
	if limitPerMin == 0 {
		return errors.New("security/ratelimit: zero limit — all calls denied")
	}

	key := agentID + "\x00" + serviceID // NUL separator avoids agent/service confusion
	now := r.clock()
	windowStart := now.Add(-time.Minute)

	r.mu.Lock()
	defer r.mu.Unlock()

	// Prune expired timestamps.
	ts := r.windows[key]
	pruned := ts[:0]
	for _, t := range ts {
		if t.After(windowStart) {
			pruned = append(pruned, t)
		}
	}

	if len(pruned) >= limitPerMin {
		r.windows[key] = pruned
		return fmt.Errorf("security/ratelimit: rate limit exceeded for agent %q service %q (%d/%d rpm)",
			agentID, serviceID, len(pruned), limitPerMin)
	}

	r.windows[key] = append(pruned, now)
	return nil
}
