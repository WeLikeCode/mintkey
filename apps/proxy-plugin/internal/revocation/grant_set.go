package revocation

import (
	"sync"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/wireid"
)

// GrantRevocationSet is a thread-safe set of revoked (agent, service) grant
// pairs. A pair is recorded from agent.permission.revoked events, and every
// token of that pair issued at or before the recorded revoked_at is refused
// for JTIRetention from revoked_at; later tokens (a new grant) are not.
//
// Source: proxy-grant-revocation design D1-D4.
type GrantRevocationSet struct {
	mu      sync.RWMutex
	revoked map[string]time.Time // canonical "agent|service" -> revoked_at
}

// NewGrantRevocationSet creates an empty GrantRevocationSet.
func NewGrantRevocationSet() *GrantRevocationSet {
	return &GrantRevocationSet{revoked: make(map[string]time.Time)}
}

// grantKey returns the map key of a pair, each id in its canonical UUID form so
// the wire form, the legacy 32-hex wire form and the dashed UUID all match.
func grantKey(agentID, serviceID string) string {
	return wireid.Canonical(agentID, "agent_") + "|" + wireid.Canonical(serviceID, "svc_")
}

// Add records the revocation for (agentID, serviceID). A later revokedAt
// replaces an earlier one, and an earlier one added afterwards changes
// nothing; an entry whose revokedAt is more than JTIRetention in the past is
// not added. Every call removes the entries that have expired.
func (s *GrantRevocationSet) Add(agentID, serviceID string, revokedAt time.Time) {
	key := grantKey(agentID, serviceID)
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	for k, t := range s.revoked {
		if !now.Before(t.Add(JTIRetention)) {
			delete(s.revoked, k)
		}
	}

	if !now.Before(revokedAt.Add(JTIRetention)) {
		return
	}
	if existing, ok := s.revoked[key]; ok && !revokedAt.After(existing) {
		return
	}
	s.revoked[key] = revokedAt
}

// Refuses reports whether a token of the pair with this iat (hasIAT false: no
// usable iat) must be refused now. A token issued at or before the recorded
// revocation second is refused; so is a token without a usable iat while an
// unexpired entry exists.
func (s *GrantRevocationSet) Refuses(agentID, serviceID string, iat int64, hasIAT bool) bool {
	key := grantKey(agentID, serviceID)
	s.mu.RLock()
	revokedAt, ok := s.revoked[key]
	s.mu.RUnlock()
	if !ok {
		return false
	}
	if !time.Now().Before(revokedAt.Add(JTIRetention)) {
		return false
	}
	if !hasIAT {
		return true
	}
	return iat <= revokedAt.Unix()
}

// Len returns the number of entries in the set.
func (s *GrantRevocationSet) Len() int {
	s.mu.RLock()
	n := len(s.revoked)
	s.mu.RUnlock()
	return n
}
