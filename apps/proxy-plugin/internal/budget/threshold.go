// Package budget — threshold tracking for audit emission.
//
// After each successful budget increment, CheckThresholds determines whether
// any alert_thresholds have been crossed and returns them. Thresholds are
// tracked per (permission_id, period_start) to avoid duplicate emissions.
//
// Source: FR-7, design §7; T-BUD-3.3.
package budget

import (
	"sync"
	"time"
)

// ThresholdTracker tracks which alert thresholds have already fired for
// each (permission_id, period_start) pair. This prevents duplicate
// budget.threshold_reached audit events within the same period.
type ThresholdTracker struct {
	mu    sync.Mutex
	fired map[string]map[int]bool // key: "permissionID|periodStart" → set of fired percentages
}

// NewThresholdTracker creates a new threshold tracker.
func NewThresholdTracker() *ThresholdTracker {
	return &ThresholdTracker{
		fired: make(map[string]map[int]bool),
	}
}

// CheckThresholds returns the thresholds that have been newly crossed based on
// the current used/ceiling values. Each threshold fires at most once per period.
//
// Parameters:
//   - permissionID: the permission grant being tracked
//   - periodStart: the period start time (used as part of the dedup key)
//   - used: current usage count (after increment)
//   - ceiling: the maximum allowed calls
//   - thresholds: the configured alert_thresholds (e.g. [50, 80, 100])
//
// Returns the list of percentage thresholds that just crossed (newly fired).
func (t *ThresholdTracker) CheckThresholds(
	permissionID string,
	periodStart time.Time,
	used, ceiling int,
	thresholds []int,
) []int {
	if ceiling <= 0 || len(thresholds) == 0 {
		return nil
	}

	pctUsed := (used * 100) / ceiling
	key := permissionID + "|" + periodStart.Format(time.RFC3339)

	t.mu.Lock()
	defer t.mu.Unlock()

	firedSet, exists := t.fired[key]
	if !exists {
		firedSet = make(map[int]bool)
		t.fired[key] = firedSet
	}

	var crossed []int
	for _, threshold := range thresholds {
		if pctUsed >= threshold && !firedSet[threshold] {
			firedSet[threshold] = true
			crossed = append(crossed, threshold)
		}
	}

	return crossed
}

// Invalidate removes all threshold tracking for the given permission_id.
// Called when budget config changes (T-BUD-3.4).
func (t *ThresholdTracker) Invalidate(permissionID string) {
	t.mu.Lock()
	defer t.mu.Unlock()

	// Remove all entries that start with this permission_id.
	for key := range t.fired {
		if len(key) > len(permissionID) && key[:len(permissionID)] == permissionID && key[len(permissionID)] == '|' {
			delete(t.fired, key)
		}
	}
}
