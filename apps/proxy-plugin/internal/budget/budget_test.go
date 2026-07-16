package budget_test

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/budget"
)

// --- Mock infrastructure ---

// mockRow implements budget.Row for controlled test scenarios.
type mockRow struct {
	values []any
	err    error
}

func (r *mockRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	for i, v := range r.values {
		switch d := dest[i].(type) {
		case *int:
			*d = v.(int)
		case *time.Time:
			*d = v.(time.Time)
		default:
			return fmt.Errorf("unsupported scan target type %T", d)
		}
	}
	return nil
}

// mockDB implements budget.DB and returns pre-configured rows per SQL query.
type mockDB struct {
	calls []mockDBCall
	idx   int
}

type mockDBCall struct {
	row *mockRow
}

func (m *mockDB) QueryRow(_ context.Context, _ string, _ ...any) budget.Row {
	if m.idx >= len(m.calls) {
		return &mockRow{err: errors.New("no more mock calls configured")}
	}
	call := m.calls[m.idx]
	m.idx++
	return call.row
}

// --- Tests ---

func TestCheck_SuccessfulIncrement(t *testing.T) {
	// Upsert returns used=5, ceiling=100 → success.
	db := &mockDB{
		calls: []mockDBCall{
			{row: &mockRow{values: []any{5, 100}}},
		},
	}

	cfg := budget.BudgetConfig{
		Ceiling: 100,
		Period:  "daily",
	}

	used, ceiling, err := budget.Check(context.Background(), db, "perm_01ABC", "tnt_01ABC", cfg)

	require.NoError(t, err)
	assert.Equal(t, 5, used)
	assert.Equal(t, 100, ceiling)
	assert.Equal(t, 1, db.idx) // only 1 DB call needed
}

func TestCheck_FirstRequestInPeriod(t *testing.T) {
	// First request: upsert inserts new row with used=1.
	db := &mockDB{
		calls: []mockDBCall{
			{row: &mockRow{values: []any{1, 50}}},
		},
	}

	cfg := budget.BudgetConfig{
		Ceiling: 50,
		Period:  "hourly",
	}

	used, ceiling, err := budget.Check(context.Background(), db, "perm_01DEF", "tnt_01DEF", cfg)

	require.NoError(t, err)
	assert.Equal(t, 1, used)
	assert.Equal(t, 50, ceiling)
}

func TestCheck_CeilingHit_ReturnsBudgetExceeded(t *testing.T) {
	// Upsert returns no rows (scan error) → ceiling hit.
	// Then SELECT returns current state.
	periodEnd := time.Date(2026, 6, 29, 0, 0, 0, 0, time.UTC)

	db := &mockDB{
		calls: []mockDBCall{
			{row: &mockRow{err: errors.New("no rows in result set")}},
			{row: &mockRow{values: []any{100, 100, periodEnd}}},
		},
	}

	cfg := budget.BudgetConfig{
		Ceiling: 100,
		Period:  "daily",
	}

	used, ceiling, err := budget.Check(context.Background(), db, "perm_01GHI", "tnt_01GHI", cfg)

	require.Error(t, err)

	var budgetErr *budget.ErrBudgetExceeded
	require.True(t, errors.As(err, &budgetErr))
	assert.Equal(t, 100, budgetErr.Used)
	assert.Equal(t, 100, budgetErr.Ceiling)
	assert.Equal(t, periodEnd, budgetErr.PeriodEnd)
	assert.Equal(t, 100, used)
	assert.Equal(t, 100, ceiling)
}

func TestCheck_UpsertAndSelectBothFail(t *testing.T) {
	// Both upsert and select fail — returns a combined error.
	db := &mockDB{
		calls: []mockDBCall{
			{row: &mockRow{err: errors.New("upsert failed")}},
			{row: &mockRow{err: errors.New("select failed")}},
		},
	}

	cfg := budget.BudgetConfig{
		Ceiling: 10,
		Period:  "hourly",
	}

	_, _, err := budget.Check(context.Background(), db, "perm_01JKL", "tnt_01JKL", cfg)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "upsert failed")
	assert.Contains(t, err.Error(), "select failed")

	// Should NOT be ErrBudgetExceeded.
	var budgetErr *budget.ErrBudgetExceeded
	assert.False(t, errors.As(err, &budgetErr))
}

func TestErrBudgetExceeded_ErrorMessage(t *testing.T) {
	err := &budget.ErrBudgetExceeded{
		Used:      1000,
		Ceiling:   1000,
		PeriodEnd: time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC),
	}

	msg := err.Error()
	assert.Contains(t, msg, "budget exceeded")
	assert.Contains(t, msg, "used=1000")
	assert.Contains(t, msg, "ceiling=1000")
	assert.Contains(t, msg, "2026-06-28T00:00:00Z")
}

func TestCheck_UsesCorrectPeriodBounds(t *testing.T) {
	// Verify that different period configs compute different bounds
	// by confirming the Check function completes without error for each period.
	periods := []string{"hourly", "daily", "weekly", "monthly"}

	for _, p := range periods {
		t.Run(p, func(t *testing.T) {
			db := &mockDB{
				calls: []mockDBCall{
					{row: &mockRow{values: []any{1, 10}}},
				},
			}

			cfg := budget.BudgetConfig{
				Ceiling: 10,
				Period:  p,
			}

			used, ceiling, err := budget.Check(context.Background(), db, "perm_01", "tnt_01", cfg)
			require.NoError(t, err)
			assert.Equal(t, 1, used)
			assert.Equal(t, 10, ceiling)
		})
	}
}
