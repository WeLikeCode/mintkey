// Package revocation provides thread-safe in-memory revocation sets for the
// Mintkey Egress Proxy plugin.
//
// Source: ADR-0014.4; T-1.6.7.
package revocation

import "sync"

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

// Add marks agentID as revoked.
func (s *AgentRevocationSet) Add(agentID string) {
	s.mu.Lock()
	s.revoked[agentID] = struct{}{}
	s.mu.Unlock()
}

// Contains reports whether agentID has been revoked.
func (s *AgentRevocationSet) Contains(agentID string) bool {
	s.mu.RLock()
	_, ok := s.revoked[agentID]
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
