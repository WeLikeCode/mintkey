// Package budget — BudgetConfigResolver resolves budget configuration for
// a given (agent_id, service_id, tenant_id) tuple.
//
// In production, the resolver maintains a local cache populated by the
// change-channel subscriber. The proxy calls Resolve before each budget check
// and skips the check when nil is returned (no budget constraint).
//
// Source: design §4 step 10.b; T-BUD-3.2.
package budget

import "sync"

// ResolvedBudget is the budget config resolved for a specific permission grant.
type ResolvedBudget struct {
	PermissionID string
	Config       BudgetConfig
}

// ConfigResolver resolves budget configuration for a given identifier set.
// Returns nil when no budget constraint exists for the grant.
type ConfigResolver interface {
	Resolve(agentID, serviceID, tenantID string) *ResolvedBudget
}

// InMemoryConfigResolver is a simple in-memory cache of budget configs keyed
// by "agentID|serviceID|tenantID". Entries are populated by the admin-api
// (via initial sync or change-channel updates) and invalidated on
// budget.config_updated events.
//
// Source: T-BUD-3.2, T-BUD-3.4.
type InMemoryConfigResolver struct {
	mu      sync.RWMutex
	configs map[string]*ResolvedBudget
}

// NewInMemoryConfigResolver creates a new resolver with an empty cache.
func NewInMemoryConfigResolver() *InMemoryConfigResolver {
	return &InMemoryConfigResolver{
		configs: make(map[string]*ResolvedBudget),
	}
}

// Set stores a budget config for the given identifiers.
func (r *InMemoryConfigResolver) Set(agentID, serviceID, tenantID string, rb *ResolvedBudget) {
	key := agentID + "|" + serviceID + "|" + tenantID
	r.mu.Lock()
	defer r.mu.Unlock()
	r.configs[key] = rb
}

// Resolve looks up the budget config for the given identifiers.
// Returns nil if no budget constraint is configured.
func (r *InMemoryConfigResolver) Resolve(agentID, serviceID, tenantID string) *ResolvedBudget {
	key := agentID + "|" + serviceID + "|" + tenantID
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.configs[key]
}

// InvalidateBudget removes all cached entries for the given permission_id.
// Called by the change-channel subscriber on budget.config_updated events.
//
// Source: T-BUD-3.4.
func (r *InMemoryConfigResolver) InvalidateBudget(permissionID string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for key, rb := range r.configs {
		if rb != nil && rb.PermissionID == permissionID {
			delete(r.configs, key)
		}
	}
}
