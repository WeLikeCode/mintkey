package jwt

import (
	"sync"
	"time"
)

const defaultRefreshTTL = 60 * time.Second

// JWKSRefreshLimiter rate-limits JWKS force-refresh per kid.
// Prevents DoS via unknown-kid hammering (ADR-0016.2).
type JWKSRefreshLimiter struct {
	mu          sync.Mutex
	lastRefresh map[string]time.Time
	ttl         time.Duration
}

// NewJWKSRefreshLimiter creates a limiter with 60s TTL.
func NewJWKSRefreshLimiter() *JWKSRefreshLimiter {
	return NewJWKSRefreshLimiterWithTTL(defaultRefreshTTL)
}

// NewJWKSRefreshLimiterWithTTL creates a limiter with a custom TTL (for testing).
func NewJWKSRefreshLimiterWithTTL(ttl time.Duration) *JWKSRefreshLimiter {
	return &JWKSRefreshLimiter{
		lastRefresh: make(map[string]time.Time),
		ttl:         ttl,
	}
}

// ShouldRefresh returns true if a JWKS refresh should be attempted for this kid.
// Returns false if a refresh was already attempted within the TTL window.
func (l *JWKSRefreshLimiter) ShouldRefresh(kid string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	last, ok := l.lastRefresh[kid]
	if ok && time.Since(last) < l.ttl {
		return false
	}
	l.lastRefresh[kid] = time.Now()
	return true
}
