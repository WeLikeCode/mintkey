// Package changes provides a stub LISTEN/NOTIFY subscriber for kong-syncer.
//
// Channels are global (not per-tenant) per ADR-0014.1:
//   - mintkey:service
//   - mintkey:agent
//
// Every caller must configure a tenant scope via WithTenantScope. Callers that
// serve all tenants (e.g. kong-syncer) pass AllTenants. Start panics on startup
// if no scope is configured — enforcing Req MT-4.
//
// Source: ADR-0014.1; design §9; T-1.0.6. LISTEN is wired in T-1.2.2.
package changes

import (
	"context"
	"log"
)

// AllTenants is the sentinel value for a global (all-tenant) subscriber.
const AllTenants = "*"

// Option configures a Client.
type Option func(*Client)

// WithTenantScope sets the tenant scope for the subscriber. Pass AllTenants for
// a global subscriber (e.g. kong-syncer). Required; Start panics without it.
func WithTenantScope(scope interface{}) Option {
	return func(c *Client) {
		c.tenantScope = scope
		c.scopeSet = true
	}
}

// Client is a stub LISTEN/NOTIFY subscriber. Real LISTEN wiring is in T-1.2.2.
type Client struct {
	db          interface{}
	tenantScope interface{}
	scopeSet    bool
}

// NewClient constructs a Client with the given options.
func NewClient(db interface{}, opts ...Option) *Client {
	c := &Client{db: db}
	for _, o := range opts {
		o(c)
	}
	return c
}

// Start blocks until ctx is done. Panics if WithTenantScope was not called,
// enforcing ADR-0014.1 / Req MT-4.
func (c *Client) Start(ctx context.Context) {
	if !c.scopeSet {
		panic("changes: WithTenantScope is required (ADR-0014.1)")
	}
	log.Printf("changes: subscriber started (scope=%v); LISTEN wired in T-1.2.2", c.tenantScope)
	<-ctx.Done()
	log.Println("changes: subscriber stopped")
}
