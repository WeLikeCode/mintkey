package revocation

import (
	"sync"
	"time"
)

// JTIRevocationSet is a thread-safe set of revoked JTI strings with bounded
// size. Has bounded size (max 100_000 entries by default) with time-based
// eviction. Populated from token.revoked events.
//
// Source: ADR-0014.4; T-1.6.7.
type JTIRevocationSet struct {
	mu      sync.RWMutex
	revoked map[string]time.Time // jti → revoked_at
	maxSize int
}

// NewJTIRevocationSet creates a JTIRevocationSet with the given capacity cap.
func NewJTIRevocationSet(maxSize int) *JTIRevocationSet {
	return &JTIRevocationSet{
		revoked: make(map[string]time.Time, maxSize),
		maxSize: maxSize,
	}
}

// Add records jti as revoked at the current time.
// If the set is at capacity, the call is a no-op (caller should call Evict
// periodically to reclaim space).
func (s *JTIRevocationSet) Add(jti string) {
	s.mu.Lock()
	if len(s.revoked) < s.maxSize {
		s.revoked[jti] = time.Now()
	}
	s.mu.Unlock()
}

// Contains reports whether jti has been revoked.
func (s *JTIRevocationSet) Contains(jti string) bool {
	s.mu.RLock()
	_, ok := s.revoked[jti]
	s.mu.RUnlock()
	return ok
}

// Len returns the number of entries in the set.
func (s *JTIRevocationSet) Len() int {
	s.mu.RLock()
	n := len(s.revoked)
	s.mu.RUnlock()
	return n
}

// Evict removes entries whose revoked_at is older than ttl.
// Call this periodically (e.g. once per JWT max-TTL) to bound memory usage.
func (s *JTIRevocationSet) Evict(ttl time.Duration) {
	cutoff := time.Now().Add(-ttl)
	s.mu.Lock()
	for jti, t := range s.revoked {
		if t.Before(cutoff) {
			delete(s.revoked, jti)
		}
	}
	s.mu.Unlock()
}
