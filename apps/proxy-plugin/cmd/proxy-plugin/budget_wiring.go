package main

import (
	"database/sql"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/budget"
)

const (
	budgetGrantCacheTTL    = 5 * time.Second // config changes reach the proxy within 5 s (S-OPS-1)
	budgetStatementTimeout = time.Second
	budgetMaxOpenConns     = 4
)

// useBudgetDB turns the budget check on: counters in db, budgets from the
// grants in db.
func (h *proxyHandler) useBudgetDB(db budget.DB) {
	h.budgetDB = db
	h.budgetResolver = budget.NewGrantResolver(db, budgetGrantCacheTTL)
}

// useBudgetSQL turns the budget check on over a Postgres pool.
func (h *proxyHandler) useBudgetSQL(db *sql.DB) {
	h.useBudgetDB(budget.NewSQLDB(db, budgetStatementTimeout))
}
