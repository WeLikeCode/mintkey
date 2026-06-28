// Package budget implements atomic call-count budget enforcement for the
// Egress Proxy plugin. It provides a single Check function that atomically
// increments a budget counter and returns the current usage, or returns
// ErrBudgetExceeded when the ceiling is hit.
//
// The package uses a lazy-init upsert pattern (INSERT...ON CONFLICT DO UPDATE)
// so that counter rows are created automatically on the first request of each
// period.
//
// Source: design §4; FR-2, FR-3, FR-4; NFR-1.
package budget

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// DB is the database interface required by the budget checker.
// It is satisfied by pgx.Pool / pgx.Conn (jackc/pgx/v5).
type DB interface {
	QueryRow(ctx context.Context, sql string, args ...any) Row
}

// Row is the interface for scanning a single row result.
// Satisfied by pgxpool.Row / pgx.Row.
type Row interface {
	Scan(dest ...any) error
}

// BudgetConfig holds the budget constraint configuration from the permission grant.
type BudgetConfig struct {
	Ceiling         int    `json:"ceiling"`
	Period          string `json:"period"`
	AlertThresholds []int  `json:"alert_thresholds"`
}

// ErrBudgetExceeded is returned when the budget ceiling has been reached for
// the current period. It carries the current state for the 429 response body.
type ErrBudgetExceeded struct {
	Used      int
	Ceiling   int
	PeriodEnd time.Time
}

func (e *ErrBudgetExceeded) Error() string {
	return fmt.Sprintf("budget exceeded: used=%d, ceiling=%d, period_end=%s",
		e.Used, e.Ceiling, e.PeriodEnd.Format(time.RFC3339))
}

// errNoRows is a sentinel used internally when the upsert returns no rows.
var errNoRows = errors.New("no rows")

// Check atomically increments the budget counter for the given permission and
// returns the current (used, ceiling) after increment. If the ceiling has been
// reached, it returns ErrBudgetExceeded.
//
// The function uses a single atomic INSERT...ON CONFLICT DO UPDATE that both
// initializes the counter lazily on the first request of a period and
// increments it. If the increment fails (0 rows — ceiling hit), it queries
// the existing counter to populate ErrBudgetExceeded.
//
// Source: design §4.
func Check(ctx context.Context, db DB, permissionID, tenantID string, cfg BudgetConfig) (used int, ceiling int, err error) {
	now := time.Now().UTC()
	periodStart, periodEnd := PeriodBounds(cfg.Period, now)

	// Atomic upsert: inserts with used=1 on first request; increments on conflict.
	// Returns nothing if used >= ceiling (WHERE clause blocks the update).
	const upsertSQL = `
		INSERT INTO budget_counters (permission_id, period_start, period_end, ceiling, used, tenant_id)
		VALUES ($1, $2, $3, $4, 1, $5)
		ON CONFLICT (permission_id, period_start) DO UPDATE
		SET used = budget_counters.used + 1
		WHERE budget_counters.used < budget_counters.ceiling
		RETURNING used, ceiling`

	row := db.QueryRow(ctx, upsertSQL, permissionID, periodStart, periodEnd, cfg.Ceiling, tenantID)
	err = row.Scan(&used, &ceiling)
	if err == nil {
		return used, ceiling, nil
	}

	// If scan failed, it means 0 rows returned (ceiling hit or errNoRows).
	// Query the existing counter to populate ErrBudgetExceeded.
	const selectSQL = `
		SELECT used, ceiling, period_end FROM budget_counters
		WHERE permission_id = $1 AND now() BETWEEN period_start AND period_end`

	var existingUsed, existingCeiling int
	var existingPeriodEnd time.Time

	selectRow := db.QueryRow(ctx, selectSQL, permissionID)
	scanErr := selectRow.Scan(&existingUsed, &existingCeiling, &existingPeriodEnd)
	if scanErr != nil {
		// If even the select fails, return the original error.
		return 0, 0, fmt.Errorf("budget: upsert failed (%w) and select failed (%w)", err, scanErr)
	}

	if existingUsed >= existingCeiling {
		return existingUsed, existingCeiling, &ErrBudgetExceeded{
			Used:      existingUsed,
			Ceiling:   existingCeiling,
			PeriodEnd: existingPeriodEnd,
		}
	}

	// Edge case: counter exists but used < ceiling — this shouldn't normally
	// happen since the upsert should have succeeded. Return the values anyway.
	return existingUsed, existingCeiling, nil
}
