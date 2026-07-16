package budget_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/budget"
)

func TestThresholdTracker_Crossing50Triggers(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	thresholds := []int{50, 80, 100}

	// At 50/100 → 50% threshold fires.
	crossed := tracker.CheckThresholds("perm_01", periodStart, 50, 100, thresholds)
	require.Len(t, crossed, 1)
	assert.Equal(t, 50, crossed[0])
}

func TestThresholdTracker_Crossing50AgainDoesNot(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	thresholds := []int{50, 80, 100}

	// First time → fires.
	crossed := tracker.CheckThresholds("perm_01", periodStart, 50, 100, thresholds)
	require.Len(t, crossed, 1)
	assert.Equal(t, 50, crossed[0])

	// Second time at same or higher usage → does NOT fire again.
	crossed = tracker.CheckThresholds("perm_01", periodStart, 55, 100, thresholds)
	assert.Empty(t, crossed)
}

func TestThresholdTracker_MultipleThresholdsCross(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	thresholds := []int{50, 80, 100}

	// Jump directly from 0 to 85% → both 50 and 80 fire.
	crossed := tracker.CheckThresholds("perm_01", periodStart, 85, 100, thresholds)
	require.Len(t, crossed, 2)
	assert.Contains(t, crossed, 50)
	assert.Contains(t, crossed, 80)
}

func TestThresholdTracker_DifferentPermissionsIndependent(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	thresholds := []int{50, 80, 100}

	// perm_01 at 50%
	crossed := tracker.CheckThresholds("perm_01", periodStart, 50, 100, thresholds)
	require.Len(t, crossed, 1)

	// perm_02 at 50% — separate tracking, should also fire.
	crossed = tracker.CheckThresholds("perm_02", periodStart, 50, 100, thresholds)
	require.Len(t, crossed, 1)
	assert.Equal(t, 50, crossed[0])
}

func TestThresholdTracker_DifferentPeriodsIndependent(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	thresholds := []int{50, 80, 100}

	period1 := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	period2 := time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC)

	// Fire in period 1.
	crossed := tracker.CheckThresholds("perm_01", period1, 50, 100, thresholds)
	require.Len(t, crossed, 1)

	// Same permission in period 2 → fires again (new period).
	crossed = tracker.CheckThresholds("perm_01", period2, 50, 100, thresholds)
	require.Len(t, crossed, 1)
	assert.Equal(t, 50, crossed[0])
}

func TestThresholdTracker_BelowThreshold_NoFire(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	thresholds := []int{50, 80, 100}

	// At 49/100 → 49% → no threshold fires.
	crossed := tracker.CheckThresholds("perm_01", periodStart, 49, 100, thresholds)
	assert.Empty(t, crossed)
}

func TestThresholdTracker_ZeroCeiling_NoFire(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	thresholds := []int{50, 80, 100}

	crossed := tracker.CheckThresholds("perm_01", periodStart, 50, 0, thresholds)
	assert.Empty(t, crossed)
}

func TestThresholdTracker_EmptyThresholds_NoFire(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)

	crossed := tracker.CheckThresholds("perm_01", periodStart, 50, 100, nil)
	assert.Empty(t, crossed)
}

func TestThresholdTracker_Invalidate(t *testing.T) {
	tracker := budget.NewThresholdTracker()
	periodStart := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	thresholds := []int{50, 80, 100}

	// Fire 50%.
	crossed := tracker.CheckThresholds("perm_01", periodStart, 50, 100, thresholds)
	require.Len(t, crossed, 1)

	// Invalidate.
	tracker.Invalidate("perm_01")

	// 50% should fire again after invalidation.
	crossed = tracker.CheckThresholds("perm_01", periodStart, 50, 100, thresholds)
	require.Len(t, crossed, 1)
	assert.Equal(t, 50, crossed[0])
}
