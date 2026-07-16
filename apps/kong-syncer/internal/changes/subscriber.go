// Package changes provides a LISTEN/NOTIFY subscriber for kong-syncer.
//
// Channels are global (not per-tenant) per ADR-0014.1:
//   - mintkey:service
//   - mintkey:agent
//
// Every caller must configure a tenant scope via WithTenantScope. Callers that
// serve all tenants (e.g. kong-syncer) pass AllTenants. Start panics on startup
// if no scope is configured — enforcing Req MT-4.
//
// Source: ADR-0014.1; design §9; T-1.0.6; T-1.2.2.
package changes

import (
	"bytes"
	"context"
	"database/sql"
	"fmt"
	"io"
	"log"
	"math/rand"
	"mime/multipart"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/lib/pq"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/kong"
	"github.com/mintkey/mintkey/services/kong-syncer/internal/wireids"
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

// WithKongAdminURL sets the Kong Admin API URL for the subscriber so it can
// push declarative config updates on mintkey:service notifications.
func WithKongAdminURL(url string) Option {
	return func(c *Client) {
		c.kongAdminURL = url
	}
}

// WithHTTPClient overrides the default HTTP client (for testing).
func WithHTTPClient(hc *http.Client) Option {
	return func(c *Client) {
		c.httpClient = hc
	}
}

// PGListener is the interface that wraps *pq.Listener for testability.
// *pq.Listener satisfies this interface via its NotificationChannel() method.
type PGListener interface {
	Listen(channel string) error
	Ping() error
	NotificationChannel() <-chan *pq.Notification
	Close() error
}

// ListenerFactory creates a PGListener from a DSN.
type ListenerFactory func(dsn string) (PGListener, error)

// WithListenerFactory allows tests to inject a mock LISTEN/NOTIFY source.
func WithListenerFactory(f ListenerFactory) Option {
	return func(c *Client) {
		c.listenerFactory = f
	}
}

// WithFetcherFn overrides the DB fetch step (for testing without a real DB).
func WithFetcherFn(fn func() ([]kong.ServiceEntry, error)) Option {
	return func(c *Client) {
		c.fetcherFn = fn
	}
}

// WithInitialRetryMaxDuration sets the cap on total wall-clock time spent
// retrying the initial reconcile. 0 means try exactly once (no retries).
func WithInitialRetryMaxDuration(d time.Duration) Option {
	return func(c *Client) {
		c.initialRetryMaxDuration = d
	}
}

// WithPeriodicInterval sets the period of the safety-net reconcile ticker.
// 0 disables the periodic safety-net entirely.
func WithPeriodicInterval(d time.Duration) Option {
	return func(c *Client) {
		c.periodicInterval = d
	}
}

// WithReconcileFn overrides the reconcile function (for testing).
func WithReconcileFn(fn func() error) Option {
	return func(c *Client) {
		c.reconcileFn = fn
	}
}

// WithNewTicker overrides the ticker constructor (for testing).
func WithNewTicker(fn func(time.Duration) *time.Ticker) Option {
	return func(c *Client) {
		c.newTicker = fn
	}
}

// WithNow overrides the clock (for testing).
func WithNow(fn func() time.Time) Option {
	return func(c *Client) {
		c.now = fn
	}
}

// WithRetryBaseBackoff overrides the initial backoff duration (for testing).
// Default is 1s. This option exists solely to make unit tests fast.
func WithRetryBaseBackoff(d time.Duration) Option {
	return func(c *Client) {
		c.retryBaseBackoff = d
	}
}

// PushStats holds mutable push counters that main.go reads for /metrics.
type PushStats struct {
	total        atomic.Int64
	lastPushSecs atomic.Int64 // Unix timestamp of last successful push; 0 = never
	lastFailed   atomic.Bool
}

// IncrTotal increments the total pushes counter and records the timestamp.
func (s *PushStats) IncrTotal() {
	s.total.Add(1)
	s.lastPushSecs.Store(time.Now().Unix())
	s.lastFailed.Store(false)
}

// MarkFailed records that the latest push attempt failed.
func (s *PushStats) MarkFailed() { s.lastFailed.Store(true) }

// Total returns the total number of successful pushes.
func (s *PushStats) Total() int64 { return s.total.Load() }

// LastPushUnix returns the Unix timestamp of the last successful push.
func (s *PushStats) LastPushUnix() int64 { return s.lastPushSecs.Load() }

// LastPushFailed returns true when the most recent push attempt failed.
func (s *PushStats) LastPushFailed() bool { return s.lastFailed.Load() }

// Client is a LISTEN/NOTIFY subscriber that reconciles Kong routes with the
// active services list whenever a mintkey:service notification arrives.
type Client struct {
	db           string // DSN string (DATABASE_URL)
	tenantScope  interface{}
	scopeSet     bool
	kongAdminURL string
	httpClient   *http.Client
	Stats        *PushStats

	// Retry / periodic config knobs.
	initialRetryMaxDuration time.Duration
	periodicInterval        time.Duration
	retryBaseBackoff        time.Duration // first backoff sleep; doubles each round

	// Overridable for testing.
	listenerFactory ListenerFactory
	fetcherFn       func() ([]kong.ServiceEntry, error)
	reconcileFn     func() error                     // defaults to c.reconcile
	newTicker       func(time.Duration) *time.Ticker // defaults to time.NewTicker
	now             func() time.Time                 // defaults to time.Now

	// mu guards lastErr; used by health handler.
	mu      sync.RWMutex
	lastErr error
}

// NewClient constructs a Client with the given options.
//
// db must be the DATABASE_URL DSN string (passed from config.Load()).
func NewClient(db interface{}, opts ...Option) *Client {
	c := &Client{
		httpClient:              &http.Client{Timeout: 30 * time.Second},
		Stats:                   &PushStats{},
		initialRetryMaxDuration: 5 * time.Minute,
		periodicInterval:        5 * time.Minute,
		retryBaseBackoff:        time.Second,
		newTicker:               time.NewTicker,
		now:                     time.Now,
	}
	if ds, ok := db.(string); ok {
		c.db = ds
	}
	for _, o := range opts {
		o(c)
	}
	// reconcileFn defaults to c.reconcile after options are applied.
	if c.reconcileFn == nil {
		c.reconcileFn = c.reconcile
	}
	return c
}

// LastErr returns the error from the most recent reconcile attempt (nil if healthy).
func (c *Client) LastErr() error {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.lastErr
}

// Start performs an initial reconcile (with exponential-backoff retry) then
// blocks listening for mintkey:service NOTIFY events, reconciling on each one.
// A periodic safety-net ticker also fires at cfg.PeriodicInterval (if > 0).
// Panics if WithTenantScope was not called, enforcing ADR-0014.1 / Req MT-4.
func (c *Client) Start(ctx context.Context) {
	if !c.scopeSet {
		panic("changes: WithTenantScope is required (ADR-0014.1)")
	}

	// --- initial reconcile with exponential backoff ------------------------
	c.initialReconcileWithRetry(ctx)

	// If no Kong admin URL is configured there is nothing to listen for.
	if c.kongAdminURL == "" || c.db == "" {
		log.Println("changes: KONG_ADMIN_URL or DATABASE_URL not set — LISTEN disabled")
		<-ctx.Done()
		log.Println("changes: subscriber stopped")
		return
	}

	// --- LISTEN loop -------------------------------------------------------
	// Skip the loop entirely if context is already done (common in tests that
	// pre-cancel the ctx to exercise only the initial reconcile path).
	if ctx.Err() != nil {
		log.Println("changes: subscriber stopped")
		return
	}

	for {
		if err := c.listenLoop(ctx); err != nil {
			if ctx.Err() != nil {
				break
			}
			log.Printf("changes: listener error (will reconnect in 5s): %v", err)
			c.setLastErr(err)
			select {
			case <-time.After(5 * time.Second):
			case <-ctx.Done():
				goto done
			}
		} else {
			// listenLoop returned nil only when ctx is done.
			break
		}
	}
done:
	log.Println("changes: subscriber stopped")
}

// initialReconcileWithRetry retries c.reconcileFn with exponential backoff
// until success or the configured max duration is exhausted. On exhaustion it
// logs a warning and returns (does NOT crash) so the LISTEN loop or a future
// periodic tick can recover.
func (c *Client) initialReconcileWithRetry(ctx context.Context) {
	startTime := c.now()
	backoff := c.retryBaseBackoff
	const maxBackoff = 256 * time.Second

	for attempt := 1; ; attempt++ {
		err := c.reconcileFn()
		if err == nil {
			elapsed := c.now().Sub(startTime).Milliseconds()
			log.Printf("level=info event=kong_sync.initial_reconcile_ok attempt=%d elapsed_ms=%d", attempt, elapsed)
			c.setLastErr(nil)
			return
		}

		c.setLastErr(err)
		elapsed := c.now().Sub(startTime)

		// Check whether we have budget for another sleep.
		if c.initialRetryMaxDuration > 0 && elapsed >= c.initialRetryMaxDuration {
			log.Printf("level=warn event=kong_sync.initial_retry_exhausted attempts=%d total_elapsed_ms=%d",
				attempt, elapsed.Milliseconds())
			return
		}

		// Apply ±25% jitter to backoff.
		jitter := time.Duration(rand.Int63n(int64(backoff/2))) - backoff/4
		sleep := backoff + jitter
		if sleep < 0 {
			sleep = backoff
		}

		// Don't sleep past the remaining budget.
		if c.initialRetryMaxDuration > 0 {
			remaining := c.initialRetryMaxDuration - elapsed
			if sleep > remaining {
				sleep = remaining
			}
		}

		log.Printf("level=info event=kong_sync.initial_retry attempt=%d elapsed_ms=%d next_backoff_ms=%d err=%q",
			attempt, elapsed.Milliseconds(), sleep.Milliseconds(), err.Error())

		select {
		case <-ctx.Done():
			log.Printf("level=warn event=kong_sync.initial_retry_exhausted attempts=%d total_elapsed_ms=%d",
				attempt, c.now().Sub(startTime).Milliseconds())
			return
		case <-time.After(sleep):
		}

		// Double backoff for next round, capped at maxBackoff.
		backoff *= 2
		if backoff > maxBackoff {
			backoff = maxBackoff
		}
	}
}

// listenLoop opens a fresh PGListener, LISTENs on mintkey:service, and
// reconciles on each incoming notification. A periodic safety-net ticker also
// calls reconcile at c.periodicInterval (when > 0). Returns nil when ctx is
// cancelled, or an error on a fatal connection problem.
func (c *Client) listenLoop(ctx context.Context) error {
	var listener PGListener

	if c.listenerFactory != nil {
		// Injected factory (used in tests).
		l, err := c.listenerFactory(c.db)
		if err != nil {
			return fmt.Errorf("listenerFactory: %w", err)
		}
		listener = l
	} else {
		// Production: real lib/pq listener.
		listener = pq.NewListener(
			c.db,
			500*time.Millisecond,
			5*time.Second,
			func(ev pq.ListenerEventType, err error) {
				if err != nil {
					log.Printf("changes: pq.Listener event=%v err=%v", ev, err)
				}
			},
		)
	}
	defer func() { _ = listener.Close() }()

	if err := listener.Listen("mintkey:service"); err != nil {
		return fmt.Errorf("LISTEN mintkey:service: %w", err)
	}
	log.Printf("changes: LISTEN mintkey:service wired (scope=%v)", c.tenantScope)

	notifyCh := listener.NotificationChannel()

	pingTicker := c.newTicker(30 * time.Second)
	defer pingTicker.Stop()

	// Periodic safety-net ticker — nil channel when disabled (0 interval).
	var periodicCh <-chan time.Time
	if c.periodicInterval > 0 {
		t := c.newTicker(c.periodicInterval)
		defer t.Stop()
		periodicCh = t.C
	}

	for {
		select {
		case <-ctx.Done():
			return nil

		case n, ok := <-notifyCh:
			if !ok {
				return fmt.Errorf("listener.Notify channel closed")
			}
			if n == nil {
				// keepalive nil notification
				continue
			}
			log.Printf("changes: received NOTIFY on %q (payload=%q) — triggering reconcile", n.Channel, n.Extra)
			if err := c.reconcileFn(); err != nil {
				log.Printf("changes: reconcile error: %v", err)
				c.setLastErr(err)
			}

		case <-periodicCh:
			c.dispatchPeriodicReconcile()

		case <-pingTicker.C:
			if err := listener.Ping(); err != nil {
				return fmt.Errorf("listener ping: %w", err)
			}
		}
	}
}

// dispatchPeriodicReconcile calls reconcileFn and logs the outcome.
func (c *Client) dispatchPeriodicReconcile() {
	start := c.now()
	if err := c.reconcileFn(); err != nil {
		log.Printf("level=error event=kong_sync.periodic_reconcile_err err=%q", err.Error())
		c.setLastErr(err)
		return
	}
	elapsed := c.now().Sub(start).Milliseconds()
	log.Printf("level=info event=kong_sync.periodic_reconcile elapsed_ms=%d", elapsed)
}

// reconcile fetches all active services from Postgres and pushes a fresh
// declarative YAML to Kong's /config endpoint.
func (c *Client) reconcile() error {
	if c.db == "" && c.fetcherFn == nil {
		return fmt.Errorf("changes: DATABASE_URL is empty, cannot reconcile")
	}
	if c.kongAdminURL == "" {
		return fmt.Errorf("changes: KONG_ADMIN_URL is empty, cannot push config")
	}

	start := time.Now()

	// --- query active services -------------------------------------------
	var entries []kong.ServiceEntry
	var err error
	if c.fetcherFn != nil {
		entries, err = c.fetcherFn()
	} else {
		entries, err = c.fetchActiveServices()
	}
	if err != nil {
		c.Stats.MarkFailed()
		return fmt.Errorf("fetchActiveServices: %w", err)
	}

	// --- generate declarative YAML ---------------------------------------
	yamlStr, err := kong.GenerateDeclarativeYAML(entries)
	if err != nil {
		c.Stats.MarkFailed()
		return fmt.Errorf("GenerateDeclarativeYAML: %w", err)
	}

	// --- POST to Kong /config --------------------------------------------
	if err := c.pushToKong(yamlStr); err != nil {
		c.Stats.MarkFailed()
		return fmt.Errorf("pushToKong: %w", err)
	}

	elapsed := time.Since(start).Milliseconds()
	c.Stats.IncrTotal()
	c.setLastErr(nil)

	log.Printf("level=info event=kong_sync routes_published=%d elapsed_ms=%d", len(entries), elapsed)
	return nil
}

// fetchActiveServices opens a standard *sql.DB connection and queries active services.
// kong-syncer is a platform-level service that needs to see all tenants, so it
// sets app.platform_admin_view = 'on' to satisfy the row-level security policy on
// the services table (same mechanism used by admin-api for cross-tenant views).
func (c *Client) fetchActiveServices() ([]kong.ServiceEntry, error) {
	db, err := sql.Open("postgres", c.db)
	if err != nil {
		return nil, fmt.Errorf("sql.Open: %w", err)
	}
	defer db.Close()

	// Use a single-use connection acquired via a transaction so the SET LOCAL
	// applies only to this query and is rolled back on conn return.
	conn, err := db.Conn(context.Background())
	if err != nil {
		return nil, fmt.Errorf("db.Conn: %w", err)
	}
	defer conn.Close()

	// Set platform_admin_view so RLS policy allows cross-tenant SELECT.
	if _, err := conn.ExecContext(context.Background(), "SET LOCAL app.platform_admin_view = 'on'"); err != nil {
		// SET LOCAL only works inside a transaction; fall through to a plain tx.
		_ = err
	}

	// Run inside a transaction so SET LOCAL applies.
	tx, err := conn.BeginTx(context.Background(), &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(context.Background(), "SET LOCAL app.platform_admin_view = 'on'"); err != nil {
		return nil, fmt.Errorf("set platform_admin_view: %w", err)
	}

	const q = `
SELECT s.id, s.tenant_id, t.slug AS tenant_slug, s.slug, s.base_url
FROM services s
JOIN tenants t ON t.id = s.tenant_id
WHERE s.status = 'active'`

	rows, err := tx.QueryContext(context.Background(), q)
	if err != nil {
		return nil, fmt.Errorf("query: %w", err)
	}
	defer rows.Close()

	var entries []kong.ServiceEntry
	for rows.Next() {
		var e kong.ServiceEntry
		if err := rows.Scan(&e.ID, &e.TenantID, &e.TenantSlug, &e.Slug, &e.BaseURL); err != nil {
			return nil, fmt.Errorf("scan: %w", err)
		}
		// Convert the raw DB UUID to the canonical svc_ wire-form ID so that
		// Kong routes are published with /v1/call/svc_<26-char Crockford> paths
		// matching the IDs returned by list_services (ADR-0017.11; OPS-GG).
		wireID, err := wireids.DBUUIDToWire(e.ID, "svc")
		if err != nil {
			return nil, fmt.Errorf("DBUUIDToWire service %q: %w", e.ID, err)
		}
		e.ID = wireID
		entries = append(entries, e)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows: %w", err)
	}
	return entries, nil
}

// pushToKong sends yamlStr to POST ${KONG_ADMIN_URL}/config?check_hash=1.
// Kong DB-less mode expects the YAML in a multipart form field named "config".
func (c *Client) pushToKong(yamlStr string) error {
	targetURL := strings.TrimRight(c.kongAdminURL, "/") + "/config?check_hash=1"

	// Build a multipart/form-data body with a single "config" field.
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	fw, err := mw.CreateFormField("config")
	if err != nil {
		return fmt.Errorf("create form field: %w", err)
	}
	if _, err := fw.Write([]byte(yamlStr)); err != nil {
		return fmt.Errorf("write form field: %w", err)
	}
	mw.Close()

	req, err := http.NewRequest(http.MethodPost, targetURL, &buf)
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("http POST: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("kong /config returned %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return nil
}

func (c *Client) setLastErr(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastErr = err
}
