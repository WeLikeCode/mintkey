package main

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/budget"
)

// budgetDBUser is the handler's ability to turn the budget check on over a
// budget DB. The tests reach it through an interface so that they name no
// symbol this change adds.
type budgetDBUser interface {
	useBudgetDB(db budget.DB)
}

// budgetSQLUser is the handler's ability to turn the budget check on over a
// Postgres pool.
type budgetSQLUser interface {
	useBudgetSQL(db *sql.DB)
}

var testAgentUUID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
var testTenantUUID = "11111111-2222-3333-4444-555555555555"
var testGrantPermissionID = "99999999-8888-7777-6666-555555555555"

func handlerWithBudgetStore(t *testing.T, db budget.DB) *proxyHandler {
	t.Helper()
	h := testHandler()
	u, ok := any(h).(budgetDBUser)
	if !ok {
		t.Fatal("proxyHandler does not implement useBudgetDB")
	}
	u.useBudgetDB(db)
	return h
}

func budgetToken(t *testing.T, h *proxyHandler, extra map[string]any) string {
	t.Helper()
	token, pub := buildScopeClaimsJWT(t, testSvcUUIDA, extra)
	h.pubKeys["testkey"] = pub
	return token
}

func uuidBudgetToken(t *testing.T, h *proxyHandler) string {
	t.Helper()
	return budgetToken(t, h, map[string]any{
		"sub": testAgentUUID,
		"tnt": testTenantUUID,
	})
}

func budgetRequest(t *testing.T, h *proxyHandler, token string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/x", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rw := httptest.NewRecorder()
	h.ServeHTTP(rw, req)
	return rw
}

// grantStoreDB is a file-local budget.DB fake backed by one grant and one
// counter row. It records every grant lookup and counter statement.
type grantStoreDB struct {
	mu sync.Mutex

	budgetJSON string
	grantErr   error
	ceiling    int
	used       int
	periodEnd  time.Time

	grantArgs    [][]any
	counterCalls int
}

func (s *grantStoreDB) QueryRow(_ context.Context, query string, args ...any) budget.Row {
	s.mu.Lock()
	defer s.mu.Unlock()

	switch {
	case strings.Contains(query, "FROM permission_grants"):
		s.grantArgs = append(s.grantArgs, append([]any(nil), args...))
		if s.grantErr != nil {
			return &grantStoreRow{err: s.grantErr}
		}
		if s.budgetJSON == "" {
			return &grantStoreRow{err: sql.ErrNoRows}
		}
		return &grantStoreRow{values: []any{testGrantPermissionID, []byte(s.budgetJSON)}}
	case strings.Contains(query, "ON CONFLICT"):
		s.counterCalls++
		if s.used < s.ceiling {
			s.used++
			return &grantStoreRow{values: []any{s.used, s.ceiling}}
		}
		return &grantStoreRow{err: sql.ErrNoRows}
	default:
		return &grantStoreRow{values: []any{s.used, s.ceiling, s.periodEnd}}
	}
}

func (s *grantStoreDB) lookups() [][]any {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([][]any, len(s.grantArgs))
	copy(out, s.grantArgs)
	return out
}

func (s *grantStoreDB) counters() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.counterCalls
}

type grantStoreRow struct {
	values []any
	err    error
}

func (r *grantStoreRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	for i, v := range r.values {
		switch d := dest[i].(type) {
		case *string:
			*d = v.(string)
		case *[]byte:
			*d = v.([]byte)
		case *int:
			*d = v.(int)
		case *time.Time:
			*d = v.(time.Time)
		default:
			return fmt.Errorf("grantStoreRow: unsupported scan target %T", d)
		}
	}
	return nil
}

// TestBudgetIsReadFromTheGrantOfTheTokenAction covers "the grant's budget is
// counted and enforced": the grant lookup uses the token's sub, aud and scope
// as UUIDs, the first call reaches the credential fetch and the second is
// refused with 429 budget_exceeded carrying the grant's permission id.
func TestBudgetIsReadFromTheGrantOfTheTokenAction_C_f99d7123(t *testing.T) {
	store := &grantStoreDB{
		budgetJSON: `{"ceiling":1,"period":"daily"}`,
		ceiling:    1,
		periodEnd:  time.Now().Add(time.Hour).UTC(),
	}
	h := handlerWithBudgetStore(t, store)
	token := uuidBudgetToken(t, h)

	first := budgetRequest(t, h, token)
	if first.Code != http.StatusBadGateway {
		t.Fatalf("first request: status = %d, want %d from the unreachable test vault (body: %s)",
			first.Code, http.StatusBadGateway, first.Body.String())
	}

	second := budgetRequest(t, h, token)
	if second.Code != http.StatusTooManyRequests {
		t.Fatalf("second request: status = %d, want %d (body: %s)",
			second.Code, http.StatusTooManyRequests, second.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(second.Body.Bytes(), &body); err != nil {
		t.Fatalf("429 body is not valid JSON: %s", second.Body.String())
	}
	if got := body["error"]; got != "budget_exceeded" {
		t.Fatalf("429 body error = %v, want %q (body: %s)", got, "budget_exceeded", second.Body.String())
	}
	if got := body["permission_id"]; got != testGrantPermissionID {
		t.Fatalf("429 body permission_id = %v, want %q", got, testGrantPermissionID)
	}

	lookups := store.lookups()
	if len(lookups) != 1 {
		t.Fatalf("grant lookups = %d, want 1 (args: %v)", len(lookups), lookups)
	}
	args := lookups[0]
	if len(args) != 3 || args[0] != testAgentUUID || args[1] != testSvcUUIDA || args[2] != "call" {
		t.Fatalf("grant lookup args = %v, want (%s, %s, call)",
			args, testAgentUUID, testSvcUUIDA)
	}
}

// TestBudgetGrantCacheIsClearedByConfigUpdate covers "a configuration change
// clears the cache": with a grant that has no budget, two cached requests cost
// one lookup, and a budget.config_updated notification makes the next request
// look the grant up again.
func TestBudgetGrantCacheIsClearedByConfigUpdate_C_5de8ad4b(t *testing.T) {
	store := &grantStoreDB{}
	h := handlerWithBudgetStore(t, store)
	token := uuidBudgetToken(t, h)

	for i := 0; i < 2; i++ {
		if rw := budgetRequest(t, h, token); rw.Code != http.StatusBadGateway {
			t.Fatalf("request %d: status = %d, want %d from the unreachable test vault (body: %s)",
				i+1, rw.Code, http.StatusBadGateway, rw.Body.String())
		}
	}
	if got := len(store.lookups()); got != 1 {
		t.Fatalf("grant lookups before the config update = %d, want 1", got)
	}

	sub := h.changesSubscriber("")
	if err := sub.HandleNotification(`{"event_type":"budget.config_updated","target_id":"perm_x"}`); err != nil {
		t.Fatalf("HandleNotification(budget.config_updated): %v", err)
	}

	if rw := budgetRequest(t, h, token); rw.Code != http.StatusBadGateway {
		t.Fatalf("third request: status = %d, want %d from the unreachable test vault (body: %s)",
			rw.Code, http.StatusBadGateway, rw.Body.String())
	}
	if got := len(store.lookups()); got != 2 {
		t.Fatalf("grant lookups after the config update = %d, want 2", got)
	}
}

// TestBudgetLookupFailureFailsOpen covers "a lookup error lets the request
// through": both requests reach the credential fetch, the failed lookup is not
// retried within the cache window, and no counter statement is issued.
func TestBudgetLookupFailureFailsOpen_C_08746266(t *testing.T) {
	store := &grantStoreDB{grantErr: errors.New("connection refused")}
	h := handlerWithBudgetStore(t, store)
	token := uuidBudgetToken(t, h)

	for i := 0; i < 2; i++ {
		if rw := budgetRequest(t, h, token); rw.Code != http.StatusBadGateway {
			t.Fatalf("request %d: status = %d, want %d from the unreachable test vault (body: %s)",
				i+1, rw.Code, http.StatusBadGateway, rw.Body.String())
		}
	}
	if got := len(store.lookups()); got != 1 {
		t.Fatalf("grant lookups = %d, want 1 (the failure is cached)", got)
	}
	if got := store.counters(); got != 0 {
		t.Fatalf("counter statements = %d, want 0", got)
	}
}

// TestBudgetLookupSkippedForNonUUIDIdentifiers covers "identifiers that are not
// UUIDs are not looked up": the request reaches the credential fetch and the
// store sees no grant lookup.
func TestBudgetLookupSkippedForNonUUIDIdentifiers_C_04da2393(t *testing.T) {
	store := &grantStoreDB{
		budgetJSON: `{"ceiling":1,"period":"daily"}`,
		ceiling:    1,
		periodEnd:  time.Now().Add(time.Hour).UTC(),
	}
	h := handlerWithBudgetStore(t, store)
	token := budgetToken(t, h, nil)

	if rw := budgetRequest(t, h, token); rw.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want %d from the unreachable test vault (body: %s)",
			rw.Code, http.StatusBadGateway, rw.Body.String())
	}
	if got := len(store.lookups()); got != 0 {
		t.Fatalf("grant lookups = %d, want 0 for non-UUID identifiers", got)
	}
}

// TestBudgetStatementsRunInTenantTransaction covers "the lookup and the counter
// run inside tenant transactions": each statement is its own BEGIN/set_config
// statement/COMMIT.
func TestBudgetStatementsRunInTenantTransaction_C_a925216c(t *testing.T) {
	budgetRecorder.reset()
	db, err := sql.Open("budgetrec", "")
	if err != nil {
		t.Fatalf("sql.Open(budgetrec): %v", err)
	}
	defer func() { _ = db.Close() }()

	h := testHandler()
	u, ok := any(h).(budgetSQLUser)
	if !ok {
		t.Fatal("proxyHandler does not implement useBudgetSQL")
	}
	u.useBudgetSQL(db)
	token := uuidBudgetToken(t, h)

	if rw := budgetRequest(t, h, token); rw.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want %d from the unreachable test vault (body: %s)",
			rw.Code, http.StatusBadGateway, rw.Body.String())
	}

	got := budgetRecorder.snapshot()
	want := []string{
		"BEGIN",
		"SET_TENANT:" + testTenantUUID,
		"GRANT",
		"COMMIT",
		"BEGIN",
		"SET_TENANT:" + testTenantUUID,
		"UPSERT",
		"COMMIT",
	}
	if len(got) != len(want) {
		t.Fatalf("recorded statements = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("recorded statements = %v, want %v", got, want)
		}
	}
}

// budgetRecorder is the file-local database/sql driver that records the
// statements the tenant-scoped SQL access issues.
var budgetRecorder = &budgetRecDriver{}

func init() {
	sql.Register("budgetrec", budgetRecorder)
}

type budgetRecDriver struct {
	mu      sync.Mutex
	records []string
}

func (d *budgetRecDriver) reset() {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.records = nil
}

func (d *budgetRecDriver) add(record string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.records = append(d.records, record)
}

func (d *budgetRecDriver) snapshot() []string {
	d.mu.Lock()
	defer d.mu.Unlock()
	out := make([]string, len(d.records))
	copy(out, d.records)
	return out
}

func (d *budgetRecDriver) Open(string) (driver.Conn, error) {
	return &budgetRecConn{rec: d}, nil
}

type budgetRecConn struct {
	rec *budgetRecDriver
}

func (c *budgetRecConn) Prepare(query string) (driver.Stmt, error) {
	return &budgetRecStmt{rec: c.rec, query: query}, nil
}

func (c *budgetRecConn) Close() error { return nil }

func (c *budgetRecConn) Begin() (driver.Tx, error) {
	c.rec.add("BEGIN")
	return &budgetRecTx{rec: c.rec}, nil
}

type budgetRecTx struct {
	rec *budgetRecDriver
}

func (t *budgetRecTx) Commit() error {
	t.rec.add("COMMIT")
	return nil
}

func (t *budgetRecTx) Rollback() error {
	t.rec.add("ROLLBACK")
	return nil
}

type budgetRecStmt struct {
	rec   *budgetRecDriver
	query string
}

func (s *budgetRecStmt) Close() error  { return nil }
func (s *budgetRecStmt) NumInput() int { return -1 }

func (s *budgetRecStmt) Exec(args []driver.Value) (driver.Result, error) {
	s.record(args)
	return driver.RowsAffected(1), nil
}

func (s *budgetRecStmt) Query(args []driver.Value) (driver.Rows, error) {
	s.record(args)
	switch {
	case strings.Contains(s.query, "FROM permission_grants"):
		return &budgetRecRows{
			cols: []string{"id", "budget"},
			data: [][]driver.Value{{
				testGrantPermissionID,
				[]byte(`{"ceiling":5,"period":"daily"}`),
			}},
		}, nil
	case strings.Contains(s.query, "INSERT INTO budget_counters"):
		return &budgetRecRows{
			cols: []string{"used", "ceiling"},
			data: [][]driver.Value{{int64(1), int64(5)}},
		}, nil
	default:
		return &budgetRecRows{cols: []string{"none"}}, nil
	}
}

func (s *budgetRecStmt) record(args []driver.Value) {
	if strings.Contains(s.query, "set_config('app.current_tenant'") {
		tenant := ""
		if len(args) > 0 {
			tenant = fmt.Sprint(args[0])
		}
		s.rec.add("SET_TENANT:" + tenant)
		return
	}
	switch {
	case strings.Contains(s.query, "FROM permission_grants"):
		s.rec.add("GRANT")
	case strings.Contains(s.query, "INSERT INTO budget_counters"):
		s.rec.add("UPSERT")
	default:
		s.rec.add("OTHER:" + strings.TrimSpace(s.query))
	}
}

type budgetRecRows struct {
	cols []string
	data [][]driver.Value
	idx  int
}

func (r *budgetRecRows) Columns() []string { return r.cols }
func (r *budgetRecRows) Close() error      { return nil }

func (r *budgetRecRows) Next(dest []driver.Value) error {
	if r.idx >= len(r.data) {
		return io.EOF
	}
	copy(dest, r.data[r.idx])
	r.idx++
	return nil
}
