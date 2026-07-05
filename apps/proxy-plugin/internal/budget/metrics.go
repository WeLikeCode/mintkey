// Package budget — Prometheus metrics for budget enforcement.
//
// Three metrics are exposed:
//   - mintkey_budget_used (gauge): current period usage after each increment.
//   - mintkey_budget_ceiling (gauge): current period ceiling when budget config is loaded.
//   - mintkey_budget_denied_total (counter): incremented on each 429 budget_exceeded.
//
// Labels: permission_id, agent_id, service_id, tenant_id.
//
// Source: NFR-5, design §9; T-BUD-3.5.
package budget

import (
	"fmt"
	"io"
	"sort"
	"sync"
	"sync/atomic"
)

// MetricLabels holds the label set for budget metrics.
type MetricLabels struct {
	PermissionID string
	AgentID      string
	ServiceID    string
	TenantID     string
}

func (l MetricLabels) key() string {
	return l.PermissionID + "|" + l.AgentID + "|" + l.ServiceID + "|" + l.TenantID
}

// BudgetMetrics holds Prometheus-format metrics for budget enforcement.
// All fields are updated via atomic operations — safe for concurrent access.
type BudgetMetrics struct {
	// usedGauges: keyed on MetricLabels.key() → *atomic.Int64
	usedGauges sync.Map

	// ceilingGauges: keyed on MetricLabels.key() → *atomic.Int64
	ceilingGauges sync.Map

	// deniedCounters: keyed on MetricLabels.key() → *atomic.Int64
	deniedCounters sync.Map

	// labelStore: keyed on MetricLabels.key() → MetricLabels (for exposition)
	labelStore sync.Map
}

// NewBudgetMetrics creates a ready-to-use BudgetMetrics instance.
func NewBudgetMetrics() *BudgetMetrics {
	return &BudgetMetrics{}
}

// SetUsed sets the mintkey_budget_used gauge to the given value.
func (m *BudgetMetrics) SetUsed(labels MetricLabels, used int) {
	key := labels.key()
	m.labelStore.LoadOrStore(key, labels)
	v, _ := m.usedGauges.LoadOrStore(key, new(atomic.Int64))
	v.(*atomic.Int64).Store(int64(used))
}

// SetCeiling sets the mintkey_budget_ceiling gauge to the given value.
func (m *BudgetMetrics) SetCeiling(labels MetricLabels, ceiling int) {
	key := labels.key()
	m.labelStore.LoadOrStore(key, labels)
	v, _ := m.ceilingGauges.LoadOrStore(key, new(atomic.Int64))
	v.(*atomic.Int64).Store(int64(ceiling))
}

// IncDenied increments the mintkey_budget_denied_total counter.
func (m *BudgetMetrics) IncDenied(labels MetricLabels) {
	key := labels.key()
	m.labelStore.LoadOrStore(key, labels)
	v, _ := m.deniedCounters.LoadOrStore(key, new(atomic.Int64))
	v.(*atomic.Int64).Add(1)
}

// WriteTo writes all budget metrics to w in Prometheus text exposition format.
func (m *BudgetMetrics) WriteTo(w io.Writer) error {
	// Collect all known label keys for deterministic output.
	keys := m.sortedKeys()

	// --- mintkey_budget_used ---
	if _, err := fmt.Fprintf(w,
		"# HELP mintkey_budget_used Current period budget usage.\n"+
			"# TYPE mintkey_budget_used gauge\n",
	); err != nil {
		return err
	}
	for _, key := range keys {
		if v, ok := m.usedGauges.Load(key); ok {
			labels := m.getLabels(key)
			if _, err := fmt.Fprintf(w,
				"mintkey_budget_used{permission_id=%q,agent_id=%q,service_id=%q,tenant_id=%q} %d\n",
				labels.PermissionID, labels.AgentID, labels.ServiceID, labels.TenantID,
				v.(*atomic.Int64).Load(),
			); err != nil {
				return err
			}
		}
	}

	// --- mintkey_budget_ceiling ---
	if _, err := fmt.Fprintf(w,
		"# HELP mintkey_budget_ceiling Current period budget ceiling.\n"+
			"# TYPE mintkey_budget_ceiling gauge\n",
	); err != nil {
		return err
	}
	for _, key := range keys {
		if v, ok := m.ceilingGauges.Load(key); ok {
			labels := m.getLabels(key)
			if _, err := fmt.Fprintf(w,
				"mintkey_budget_ceiling{permission_id=%q,agent_id=%q,service_id=%q,tenant_id=%q} %d\n",
				labels.PermissionID, labels.AgentID, labels.ServiceID, labels.TenantID,
				v.(*atomic.Int64).Load(),
			); err != nil {
				return err
			}
		}
	}

	// --- mintkey_budget_denied_total ---
	if _, err := fmt.Fprintf(w,
		"# HELP mintkey_budget_denied_total Total budget-denied requests.\n"+
			"# TYPE mintkey_budget_denied_total counter\n",
	); err != nil {
		return err
	}
	for _, key := range keys {
		if v, ok := m.deniedCounters.Load(key); ok {
			labels := m.getLabels(key)
			if _, err := fmt.Fprintf(w,
				"mintkey_budget_denied_total{permission_id=%q,agent_id=%q,service_id=%q,tenant_id=%q} %d\n",
				labels.PermissionID, labels.AgentID, labels.ServiceID, labels.TenantID,
				v.(*atomic.Int64).Load(),
			); err != nil {
				return err
			}
		}
	}

	return nil
}

// sortedKeys returns all stored label keys sorted for deterministic output.
func (m *BudgetMetrics) sortedKeys() []string {
	var keys []string
	m.labelStore.Range(func(k, _ any) bool {
		keys = append(keys, k.(string))
		return true
	})
	sort.Strings(keys)
	return keys
}

// getLabels retrieves the MetricLabels for a given key.
func (m *BudgetMetrics) getLabels(key string) MetricLabels {
	v, ok := m.labelStore.Load(key)
	if !ok {
		return MetricLabels{}
	}
	return v.(MetricLabels)
}
