// Package revocation provides thread-safe in-memory revocation sets for the
// Mintkey Egress Proxy plugin.
//
// Source: ADR-0014.4; T-1.6.7.
package revocation

import (
	"sync"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/wireid"
)

// AgentRevocationSet is a thread-safe set of revoked agent IDs.
// Populated by the change channel subscriber from agent.revoked events.
type AgentRevocationSet struct {
	mu      sync.RWMutex
	revoked map[string]struct{}
}

// NewAgentRevocationSet creates an empty AgentRevocationSet.
func NewAgentRevocationSet() *AgentRevocationSet {
	return &AgentRevocationSet{revoked: make(map[string]struct{})}
}

// Add marks agentID as revoked. Ids are keyed by their canonical UUID form, so
// the wire form, the legacy 32-hex wire form and the dashed UUID all match.
// Add("") adds nothing.
func (s *AgentRevocationSet) Add(agentID string) {
	if agentID == "" {
		return
	}
	key := wireid.Canonical(agentID, "agent_")
	s.mu.Lock()
	s.revoked[key] = struct{}{}
	s.mu.Unlock()
}

// Contains reports whether agentID has been revoked.
func (s *AgentRevocationSet) Contains(agentID string) bool {
	key := wireid.Canonical(agentID, "agent_")
	s.mu.RLock()
	_, ok := s.revoked[key]
	s.mu.RUnlock()
	return ok
}

// Len returns the number of entries in the set.
func (s *AgentRevocationSet) Len() int {
	s.mu.RLock()
	n := len(s.revoked)
	s.mu.RUnlock()
	return n
}
