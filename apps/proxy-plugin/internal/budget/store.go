package budget

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"log"
	"sync"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/wireid"
)

// ActionResolver resolves the budget of the grant of one action. The proxy
// prefers it over ConfigResolver.
type ActionResolver interface {
	ResolveAction(ctx context.Context, agentID, serviceID, tenantID, action string) *ResolvedBudget
}

// GrantBudgetSQL reads the budget of the permission grant of one
// (agent, service, action). Only an object-valued budget is returned.
const GrantBudgetSQL = `SELECT id::text, constraints->'budget' FROM permission_grants
WHERE agent_id = $1 AND service_id = $2 AND action = $3 AND jsonb_typeof(constraints->'budget') = 'object'
LIMIT 1`

// SetTenantSQL sets the row-level security tenant for the current transaction.
const SetTenantSQL = `SELECT set_config('app.current_tenant', $1, true)`

// ErrNoTenant is returned when a tenant-scoped statement runs without a tenant
// in its context.
var ErrNoTenant = errors.New("budget: no tenant in context")

type tenantKey struct{}

// WithTenant returns ctx carrying tenantID for the tenant-scoped SQL access.
func WithTenant(ctx context.Context, tenantID string) context.Context {
	return context.WithValue(ctx, tenantKey{}, tenantID)
}

// TenantFrom returns the tenant carried by ctx, or "" when absent.
func TenantFrom(ctx context.Context) string {
	v, _ := ctx.Value(tenantKey{}).(string)
	return v
}

type grantEntry struct {
	resolved *ResolvedBudget
	at       time.Time
}

// GrantResolver reads budgets from permission_grants through db and caches each
// answer, a budget or none, for ttl.
type GrantResolver struct {
	db    DB
	ttl   time.Duration
	now   func() time.Time
	mu    sync.Mutex
	cache map[string]grantEntry
}

// NewGrantResolver creates a resolver over db whose answers live for ttl.
func NewGrantResolver(db DB, ttl time.Duration) *GrantResolver {
	return &GrantResolver{
		db:    db,
		ttl:   ttl,
		now:   time.Now,
		cache: make(map[string]grantEntry),
	}
}

// ResolveAction returns the budget of the grant of action for the identifiers,
// or nil when there is none or the identifiers are not decodable.
func (g *GrantResolver) ResolveAction(ctx context.Context, agentID, serviceID, tenantID, action string) *ResolvedBudget {
	a, ok := wireid.ToUUID(agentID, "agent_")
	if !ok {
		return nil
	}
	s, ok := wireid.ToUUID(serviceID, "svc_")
	if !ok {
		return nil
	}
	t, ok := wireid.ToUUID(tenantID, "tenant_")
	if !ok {
		return nil
	}
	if action == "" {
		return nil
	}

	key := a + "|" + s + "|" + t + "|" + action
	now := g.now()
	g.mu.Lock()
	if entry, found := g.cache[key]; found && now.Sub(entry.at) < g.ttl {
		g.mu.Unlock()
		return entry.resolved
	}
	g.mu.Unlock()

	resolved := g.lookup(ctx, a, s, t, action)

	g.mu.Lock()
	g.cache[key] = grantEntry{resolved: resolved, at: now}
	g.mu.Unlock()
	return resolved
}

func (g *GrantResolver) lookup(ctx context.Context, agentUUID, serviceUUID, tenantUUID, action string) *ResolvedBudget {
	lookupCtx, cancel := context.WithTimeout(ctx, time.Second)
	defer cancel()

	var permissionID string
	var raw []byte
	err := g.db.QueryRow(WithTenant(lookupCtx, tenantUUID), GrantBudgetSQL, agentUUID, serviceUUID, action).
		Scan(&permissionID, &raw)
	if err != nil {
		if !errors.Is(err, sql.ErrNoRows) {
			log.Printf("proxy-plugin: budget grant lookup failed: %v", err)
		}
		return nil
	}

	var cfg BudgetConfig
	if err := json.Unmarshal(raw, &cfg); err != nil {
		return nil
	}
	if cfg.Ceiling < 1 {
		return nil
	}
	return &ResolvedBudget{PermissionID: permissionID, Config: cfg}
}

// Resolve always returns nil: GrantResolver resolves per action, not per
// (agent, service, tenant).
func (g *GrantResolver) Resolve(agentID, serviceID, tenantID string) *ResolvedBudget {
	return nil
}

// InvalidateBudget clears every cached answer.
func (g *GrantResolver) InvalidateBudget(permissionID string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.cache = make(map[string]grantEntry)
}

// SQLDB runs each statement in its own transaction that first runs SetTenantSQL
// with TenantFrom(ctx).
type SQLDB struct {
	db      *sql.DB
	timeout time.Duration
}

// NewSQLDB creates tenant-scoped SQL access over db with a per-statement
// timeout.
func NewSQLDB(db *sql.DB, timeout time.Duration) *SQLDB {
	return &SQLDB{db: db, timeout: timeout}
}

// QueryRow returns a Row whose Scan runs the statement in its tenant
// transaction.
func (s *SQLDB) QueryRow(ctx context.Context, query string, args ...any) Row {
	return &sqlRow{db: s.db, ctx: ctx, query: query, args: args, timeout: s.timeout}
}

type sqlRow struct {
	db      *sql.DB
	ctx     context.Context
	query   string
	args    []any
	timeout time.Duration
}

func (r *sqlRow) Scan(dest ...any) error {
	tenant := TenantFrom(r.ctx)
	if tenant == "" {
		return ErrNoTenant
	}

	ctx, cancel := context.WithTimeout(r.ctx, r.timeout)
	defer cancel()

	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, SetTenantSQL, tenant); err != nil {
		_ = tx.Rollback()
		return err
	}
	if err := tx.QueryRowContext(ctx, r.query, r.args...).Scan(dest...); err != nil {
		_ = tx.Rollback()
		return err
	}
	return tx.Commit()
}
