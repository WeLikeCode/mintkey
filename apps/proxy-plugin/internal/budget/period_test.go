package budget_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/budget"
)

func TestPeriodBounds_Hourly(t *testing.T) {
	// 14:37:22 UTC → [14:00, 15:00)
	ref := time.Date(2026, 6, 28, 14, 37, 22, 0, time.UTC)
	start, end := budget.PeriodBounds("hourly", ref)

	assert.Equal(t, time.Date(2026, 6, 28, 14, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2026, 6, 28, 15, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_Hourly_Midnight(t *testing.T) {
	// Midnight edge: 00:00:00 → [00:00, 01:00)
	ref := time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC)
	start, end := budget.PeriodBounds("hourly", ref)

	assert.Equal(t, time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2026, 6, 28, 1, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_Daily(t *testing.T) {
	ref := time.Date(2026, 6, 28, 14, 37, 22, 0, time.UTC)
	start, end := budget.PeriodBounds("daily", ref)

	assert.Equal(t, time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2026, 6, 29, 0, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_Weekly_Wednesday(t *testing.T) {
	// Wednesday 2026-07-01 → Monday 2026-06-29 to Sunday 2026-07-06
	ref := time.Date(2026, 7, 1, 10, 30, 0, 0, time.UTC) // Wednesday
	start, end := budget.PeriodBounds("weekly", ref)

	assert.Equal(t, time.Date(2026, 6, 29, 0, 0, 0, 0, time.UTC), start)  // Monday
	assert.Equal(t, time.Date(2026, 7, 6, 0, 0, 0, 0, time.UTC), end)     // Next Monday
}

func TestPeriodBounds_Weekly_Monday(t *testing.T) {
	// Monday itself → same Monday start
	ref := time.Date(2026, 6, 29, 0, 0, 0, 0, time.UTC) // Monday
	start, end := budget.PeriodBounds("weekly", ref)

	assert.Equal(t, time.Date(2026, 6, 29, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2026, 7, 6, 0, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_Weekly_Sunday(t *testing.T) {
	// Sunday 2026-07-05 → still belongs to week starting Monday 2026-06-29
	ref := time.Date(2026, 7, 5, 23, 59, 59, 0, time.UTC) // Sunday
	start, end := budget.PeriodBounds("weekly", ref)

	assert.Equal(t, time.Date(2026, 6, 29, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2026, 7, 6, 0, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_Monthly(t *testing.T) {
	ref := time.Date(2026, 6, 15, 12, 0, 0, 0, time.UTC)
	start, end := budget.PeriodBounds("monthly", ref)

	assert.Equal(t, time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_Monthly_February(t *testing.T) {
	// Feb 2024 (leap year) → March 1
	ref := time.Date(2024, 2, 15, 0, 0, 0, 0, time.UTC)
	start, end := budget.PeriodBounds("monthly", ref)

	assert.Equal(t, time.Date(2024, 2, 1, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2024, 3, 1, 0, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_Monthly_December(t *testing.T) {
	// December → next month is January of next year
	ref := time.Date(2026, 12, 25, 0, 0, 0, 0, time.UTC)
	start, end := budget.PeriodBounds("monthly", ref)

	assert.Equal(t, time.Date(2026, 12, 1, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2027, 1, 1, 0, 0, 0, 0, time.UTC), end)
}

func TestPeriodBounds_UnknownPeriod_FallsBackToDaily(t *testing.T) {
	ref := time.Date(2026, 6, 28, 14, 37, 22, 0, time.UTC)
	start, end := budget.PeriodBounds("unknown", ref)

	assert.Equal(t, time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC), start)
	assert.Equal(t, time.Date(2026, 6, 29, 0, 0, 0, 0, time.UTC), end)
}
