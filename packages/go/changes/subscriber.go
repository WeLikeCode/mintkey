// Package changes provides the shared LISTEN/NOTIFY client with mandatory
// per-tenant scope enforcement (ADR-0014.1).
//
// Channels are global — never per-tenant:
//   - mintkey:service
//   - mintkey:credential
//   - mintkey:agent
//   - mintkey:heartbeat
//
// Each event payload carries tenant_id; filtering is applied at the application
// layer inside this package.
package changes

import (
	"context"
	"encoding/json"
	"sync"
	"time"
)

// Channels this package listens on (global, not per-tenant — ADR-0014.1).
var defaultChannels = []string{
	"mintkey:service",
	"mintkey:credential",
	"mintkey:agent",
	"mintkey:heartbeat",
}

// defaultHeartbeatTimeout is the maximum idle period before a reconnect is
// triggered.
const defaultHeartbeatTimeout = 60 * time.Second

// -----------------------------------------------------------------------------
// TenantScope
// -----------------------------------------------------------------------------

// TenantScope restricts which tenant events a subscriber receives.
// Callers must pass exactly one of AllTenants or NewSpecificTenantsScope(...).
type TenantScope interface {
	isTenantScope()
}

// allTenantsScope is the sentinel used by cross-tenant subscribers such as
// kong-syncer.
type allTenantsScope struct{}

func (allTenantsScope) isTenantScope() {}

// AllTenants is the sentinel TenantScope value that disables per-tenant
// filtering.
var AllTenants TenantScope = allTenantsScope{}

// specificTenantsScope restricts delivery to a fixed set of tenant IDs.
type specificTenantsScope struct {
	tenantIDs map[string]struct{}
}

func (specificTenantsScope) isTenantScope() {}

// NewSpecificTenantsScope builds a TenantScope that accepts only events whose
// tenant_id is in the provided list.
func NewSpecificTenantsScope(ids []string) TenantScope {
	m := make(map[string]struct{}, len(ids))
	for _, id := range ids {
		m[id] = struct{}{}
	}
	return specificTenantsScope{tenantIDs: m}
}

// -----------------------------------------------------------------------------
// Options
// -----------------------------------------------------------------------------

type options struct {
	scope                TenantScope
	reconnectHook        func()
	eventHandler         func(channel, payload string)
	lastActivityOverride *time.Time
	heartbeatInterval    time.Duration
}

// Option is a functional option for NewClient.
type Option func(*options)

// WithTenantScope configures the tenant filter. Must be called before Start().
func WithTenantScope(scope TenantScope) Option {
	return func(o *options) { o.scope = scope }
}

// WithReconnectHook registers a callback that is invoked each time the client
// decides to reconnect (e.g., after a heartbeat timeout). Intended for testing.
func WithReconnectHook(fn func()) Option {
	return func(o *options) { o.reconnectHook = fn }
}

// WithEventHandler registers a callback that is invoked for each event that
// passes the tenant filter.
func WithEventHandler(fn func(channel, payload string)) Option {
	return func(o *options) { o.eventHandler = fn }
}

// WithLastActivityOverride sets an explicit "last activity" timestamp so tests
// can simulate a stale connection without sleeping.
func WithLastActivityOverride(t time.Time) Option {
	return func(o *options) { o.lastActivityOverride = &t }
}

// WithHeartbeatInterval overrides the interval at which the heartbeat checker
// polls. Defaults to 10 s; tests pass a much shorter value.
func WithHeartbeatInterval(d time.Duration) Option {
	return func(o *options) { o.heartbeatInterval = d }
}

// -----------------------------------------------------------------------------
// Client
// -----------------------------------------------------------------------------

// Client is the shared LISTEN/NOTIFY subscriber. The pgx connection is typed
// as interface{} because full pgx integration is wired in T-1.2.2; this
// package provides all non-IO logic now so it is fully testable without a
// live database.
type Client struct {
	db   interface{}
	opts options

	mu           sync.Mutex
	lastActivity time.Time
}

// NewClient creates a new Client. At least WithTenantScope must be passed
// before calling Start(); the client panics otherwise (ADR-0014.1).
func NewClient(db interface{}, opts ...Option) *Client {
	c := &Client{
		db:           db,
		lastActivity: time.Now(),
	}
	c.opts.heartbeatInterval = 10 * time.Second
	for _, opt := range opts {
		opt(&c.opts)
	}
	// Allow tests to override the initial last-activity timestamp.
	if c.opts.lastActivityOverride != nil {
		c.lastActivity = *c.opts.lastActivityOverride
	}
	return c
}

// Start blocks until ctx is cancelled, enforcing the heartbeat/reconnect loop.
// It panics immediately if WithTenantScope was not called.
//
// In T-1.2.2, Start will also open the pgx connection and issue LISTEN
// commands. For now only the heartbeat monitor and tenant-filter logic are
// implemented (the LISTEN stub path).
func (c *Client) Start(ctx context.Context) {
	if c.opts.scope == nil {
		panic("changes: WithTenantScope is required (ADR-0014.1)")
	}
	c.heartbeatLoop(ctx)
}

// heartbeatLoop runs a periodic check: if no activity has been seen within
// defaultHeartbeatTimeout (or the configured heartbeatInterval), it triggers a
// reconnect.
func (c *Client) heartbeatLoop(ctx context.Context) {
	ticker := time.NewTicker(c.opts.heartbeatInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			c.mu.Lock()
			idle := time.Since(c.lastActivity)
			c.mu.Unlock()

			if idle >= defaultHeartbeatTimeout {
				c.reconnect(ctx)
			}
		}
	}
}

// reconnect is called when the heartbeat timeout fires. It updates the last
// activity time, calls the reconnect hook (if any), and — once T-1.2.2 wires
// the real pgx connection — will call the admin-api reconciliation endpoint
// GET /v1/changes?since=<last_event_id> to replay missed events.
func (c *Client) reconnect(_ context.Context) {
	c.mu.Lock()
	c.lastActivity = time.Now()
	c.mu.Unlock()

	if c.opts.reconnectHook != nil {
		c.opts.reconnectHook()
	}
	// TODO T-1.2.2: re-dial pgx, re-issue LISTEN, fetch missed events via
	// GET /v1/changes?since=<lastEventID>.
}

// InjectEvent delivers a synthetic notification as if it arrived from
// PostgreSQL LISTEN/NOTIFY. The event is only forwarded to the handler if it
// passes the tenant filter.
//
// This is the test-injection surface; production code will not call it.
func (c *Client) InjectEvent(channel, payload string) {
	if !c.passesFilter(payload) {
		return
	}
	c.mu.Lock()
	c.lastActivity = time.Now()
	c.mu.Unlock()

	if c.opts.eventHandler != nil {
		c.opts.eventHandler(channel, payload)
	}
}

// passesFilter returns true if the event payload's tenant_id is within the
// configured scope.
func (c *Client) passesFilter(payload string) bool {
	switch c.opts.scope.(type) {
	case allTenantsScope:
		return true
	case specificTenantsScope:
		sc := c.opts.scope.(specificTenantsScope)
		var env struct {
			TenantID string `json:"tenant_id"`
		}
		if err := json.Unmarshal([]byte(payload), &env); err != nil {
			// Malformed payload: drop.
			return false
		}
		_, ok := sc.tenantIDs[env.TenantID]
		return ok
	default:
		// Unknown scope type: drop conservatively.
		return false
	}
}

// Channels returns the list of PostgreSQL channels this client listens on.
// Exposed so callers (T-1.2.2) can issue LISTEN commands.
func Channels() []string {
	return append([]string(nil), defaultChannels...)
}
