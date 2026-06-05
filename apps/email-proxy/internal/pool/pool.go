// Package pool provides a per-(tenant, service) connection pool for outbound
// IMAP clients.
//
// Each (tenantID, serviceID) pair owns a PerServicePool capped at MaxConns
// (default 5). Connections idle for longer than IdleTimeout (default 5 min)
// are closed and removed.
//
// Thread safety: all exported methods are safe for concurrent use.
package pool

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
)

const (
	// DefaultMaxConns is the default maximum connections per (tenant, service).
	DefaultMaxConns = 5
	// DefaultIdleTimeout is the default idle connection lifetime.
	DefaultIdleTimeout = 5 * time.Minute
)

// poolKey uniquely identifies a (tenantID, serviceID) pair.
type poolKey struct {
	TenantID  string
	ServiceID string
}

// pooledConn wraps an IMAP Client with idle-tracking metadata.
type pooledConn struct {
	client    *imapwrap.Client
	lastUsed  time.Time
}

// PerServicePool is the per-(tenant, service) connection pool.
type PerServicePool struct {
	mu                    sync.Mutex
	key                   poolKey
	creds                 imapwrap.Credentials
	dialMode              imapwrap.DialMode
	addr                  string
	maxConns              int
	idleTimeout           time.Duration
	tlsInsecureSkipVerify bool // per-service TLS cert bypass (ADR-0024)

	idle   []*pooledConn // available connections
	active int           // count of leased connections
}

// newPerServicePool creates an empty PerServicePool.
func newPerServicePool(key poolKey, addr string, mode imapwrap.DialMode, creds imapwrap.Credentials, maxConns int, idleTimeout time.Duration, tlsInsecureSkipVerify bool) *PerServicePool {
	return &PerServicePool{
		key:                   key,
		addr:                  addr,
		creds:                 creds,
		dialMode:              mode,
		maxConns:              maxConns,
		idleTimeout:           idleTimeout,
		tlsInsecureSkipVerify: tlsInsecureSkipVerify,
	}
}

// get returns a client from the pool, creating a new one if needed.
// Returns ErrPoolExhausted if the cap is reached and no idle connection is available.
func (p *PerServicePool) get(ctx context.Context, dialFn dialFunc) (*imapwrap.Client, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	now := time.Now()

	// Evict timed-out idle connections.
	p.evictIdleLocked(now)

	// Prefer an existing idle connection.
	if len(p.idle) > 0 {
		pc := p.idle[len(p.idle)-1]
		p.idle = p.idle[:len(p.idle)-1]
		p.active++
		return pc.client, nil
	}

	// At cap — fail fast.
	if p.active >= p.maxConns {
		return nil, ErrPoolExhausted
	}

	// Open a new connection.
	c, err := dialFn(ctx, p.addr, p.dialMode, p.creds, p.tlsInsecureSkipVerify)
	if err != nil {
		return nil, fmt.Errorf("pool: dial %s: %w", p.addr, err)
	}
	p.active++
	return c, nil
}

// release returns a client to the pool.  If the client is unhealthy
// (ping fails) it is closed and evicted.
func (p *PerServicePool) release(c *imapwrap.Client) {
	p.mu.Lock()
	defer p.mu.Unlock()

	p.active--

	if err := c.Ping(); err != nil {
		// Unhealthy — discard.
		_ = c.Close()
		return
	}

	p.idle = append(p.idle, &pooledConn{client: c, lastUsed: time.Now()})
}

// evictIdleLocked removes expired idle connections. Must be called with p.mu held.
func (p *PerServicePool) evictIdleLocked(now time.Time) {
	var keep []*pooledConn
	for _, pc := range p.idle {
		if now.Sub(pc.lastUsed) < p.idleTimeout {
			keep = append(keep, pc)
		} else {
			_ = pc.client.Close()
		}
	}
	p.idle = keep
}

// closeAll closes all idle connections. Must be called with mu held.
func (p *PerServicePool) closeAll() {
	for _, pc := range p.idle {
		_ = pc.client.Close()
	}
	p.idle = nil
}

// idleCount returns the number of currently idle connections (test helper).
func (p *PerServicePool) idleCount() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.idle)
}

// activeCount returns the number of leased connections (test helper).
func (p *PerServicePool) activeCount() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.active
}

// ErrPoolExhausted is returned when Get is called and all MaxConns slots are
// already leased.
var ErrPoolExhausted = errors.New("pool: connection pool exhausted")

// dialFunc is the function signature for opening a new IMAP connection.
// insecureSkipVerify disables TLS certificate verification (ADR-0024).
// Abstracted so tests can inject a fake dialer.
type dialFunc func(ctx context.Context, addr string, mode imapwrap.DialMode, creds imapwrap.Credentials, insecureSkipVerify bool) (*imapwrap.Client, error)

// Options configures the Pool.
type Options struct {
	// MaxConns is the maximum number of connections per (tenant, service).
	// Default: DefaultMaxConns (5).
	MaxConns int
	// IdleTimeout is the maximum idle duration before a connection is closed.
	// Default: DefaultIdleTimeout (5 min).
	IdleTimeout time.Duration
}

func (o *Options) maxConns() int {
	if o == nil || o.MaxConns <= 0 {
		return DefaultMaxConns
	}
	return o.MaxConns
}

func (o *Options) idleTimeout() time.Duration {
	if o == nil || o.IdleTimeout <= 0 {
		return DefaultIdleTimeout
	}
	return o.IdleTimeout
}

// Pool manages per-(tenant, service) PerServicePools.
type Pool struct {
	mu      sync.Mutex
	pools   map[poolKey]*PerServicePool
	opts    *Options
	dialFn  dialFunc
}

// New creates a new Pool with the given options.
// Pass nil to use defaults.
func New(opts *Options) *Pool {
	return &Pool{
		pools:  make(map[poolKey]*PerServicePool),
		opts:   opts,
		dialFn: realDial,
	}
}

// newWithDialer creates a Pool with a custom dial function (for tests).
func newWithDialer(opts *Options, fn dialFunc) *Pool {
	p := New(opts)
	p.dialFn = fn
	return p
}

// ServiceConfig holds connection parameters for a single email service.
type ServiceConfig struct {
	TenantID              string
	ServiceID             string
	Addr                  string
	DialMode              imapwrap.DialMode
	Creds                 imapwrap.Credentials
	TlsInsecureSkipVerify bool // per-service TLS cert bypass (ADR-0024)
}

// Get returns a leased IMAP client for the given (tenant, service).
// The caller MUST call Release when done.
func (p *Pool) Get(ctx context.Context, cfg ServiceConfig) (*imapwrap.Client, error) {
	if cfg.TenantID == "" {
		return nil, errors.New("pool: Get: TenantID is empty")
	}
	if cfg.ServiceID == "" {
		return nil, errors.New("pool: Get: ServiceID is empty")
	}

	sp := p.getOrCreateServicePool(cfg)
	return sp.get(ctx, p.dialFn)
}

// Release returns a client back to its pool. It is safe to call with a nil
// client (no-op).
func (p *Pool) Release(cfg ServiceConfig, c *imapwrap.Client) {
	if c == nil {
		return
	}
	key := poolKey{TenantID: cfg.TenantID, ServiceID: cfg.ServiceID}

	p.mu.Lock()
	sp, ok := p.pools[key]
	p.mu.Unlock()

	if !ok {
		// Pool was destroyed — just close.
		_ = c.Close()
		return
	}
	sp.release(c)
}

// Close shuts down the pool, closing all idle connections.
func (p *Pool) Close() {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, sp := range p.pools {
		sp.mu.Lock()
		sp.closeAll()
		sp.mu.Unlock()
	}
	p.pools = make(map[poolKey]*PerServicePool)
}

// credsEquivalent reports whether two Credentials sets are equivalent
// for pool-reuse purposes. A mismatch on any auth-relevant field forces
// the pool to be rebuilt so that fresh credentials reach the next dial.
func credsEquivalent(a, b imapwrap.Credentials) bool {
	return a.Username == b.Username &&
		a.AuthMode == b.AuthMode &&
		a.AccessToken == b.AccessToken &&
		a.Password == b.Password
}

func (p *Pool) getOrCreateServicePool(cfg ServiceConfig) *PerServicePool {
	key := poolKey{TenantID: cfg.TenantID, ServiceID: cfg.ServiceID}

	p.mu.Lock()
	defer p.mu.Unlock()

	if sp, ok := p.pools[key]; ok {
		if credsEquivalent(sp.creds, cfg.Creds) {
			return sp
		}
		// Creds rotated (OAuth2 re-auth, password change, XOAUTH2 token
		// refresh) — close the stale pool's idle connections and rebuild
		// so the next dial uses the new credentials.
		sp.mu.Lock()
		sp.closeAll()
		sp.mu.Unlock()
		delete(p.pools, key)
	}

	sp := newPerServicePool(key, cfg.Addr, cfg.DialMode, cfg.Creds, p.opts.maxConns(), p.opts.idleTimeout(), cfg.TlsInsecureSkipVerify)
	p.pools[key] = sp
	return sp
}

// realDial is the production dial implementation.
func realDial(ctx context.Context, addr string, mode imapwrap.DialMode, creds imapwrap.Credentials, insecureSkipVerify bool) (*imapwrap.Client, error) {
	return imapwrap.Dial(ctx, addr, mode, creds, insecureSkipVerify)
}
