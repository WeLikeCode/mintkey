//go:build integration

// Package integration contains end-to-end integration tests for the email-proxy.
//
// These tests spin up real in-process infrastructure:
//   - github.com/emersion/go-imap/v2/imapserver/imapmemserver — in-process IMAP server
//   - net/http/httptest — OAuth2 mock admin-api server
//   - Stub SMTPSender (captures send calls; no real TLS needed)
//
// Build tag: integration
//
// Run with:
//
//	cd apps/email-proxy && go test -tags=integration ./tests/integration/... -v -count=1
//
// These tests are excluded from the default `go test ./...` run.
package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	goiMAP "github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
	"github.com/emersion/go-imap/v2/imapserver"
	"github.com/emersion/go-imap/v2/imapserver/imapmemserver"

	authpkg "github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
	"github.com/mintkey/mintkey/services/email-proxy/internal/oauth2"
	"github.com/mintkey/mintkey/services/email-proxy/internal/pool"
	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server/handlers"
	"github.com/mintkey/mintkey/services/email-proxy/internal/smtp"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

// ============================================================================
// Test constants
// ============================================================================

const (
	itUser      = "alice"
	itPass      = "letmein"
	itTenantID  = "tenant_integration_01"
	itServiceID = "svc_integration_01"
	itAgentID   = "agent_integration_01"
	itInbox     = "INBOX"
	itArchive   = "Archive"

	itRawMsg = "MIME-Version: 1.0\r\nSubject: Integration Test\r\nFrom: alice@example.com\r\nTo: bob@example.com\r\n\r\nBody: integration test content."
)

// ============================================================================
// In-process IMAP server helpers
// ============================================================================

// startIMAPServer launches an imapmemserver on a random port and returns
// its address, the user object (for appending messages), and a cleanup fn.
func startIMAPServer(t *testing.T) (addr string, user *imapmemserver.User, cleanup func()) {
	t.Helper()

	memSrv := imapmemserver.New()
	u := imapmemserver.NewUser(itUser, itPass)
	if err := u.Create(itInbox, nil); err != nil {
		t.Fatalf("startIMAPServer: create INBOX: %v", err)
	}
	if err := u.Create(itArchive, nil); err != nil {
		t.Fatalf("startIMAPServer: create Archive: %v", err)
	}
	memSrv.AddUser(u)

	srv := imapserver.New(&imapserver.Options{
		NewSession: func(_ *imapserver.Conn) (imapserver.Session, *imapserver.GreetingData, error) {
			return memSrv.NewSession(), nil, nil
		},
		InsecureAuth: true,
		Caps: goiMAP.CapSet{
			goiMAP.CapIMAP4rev1: {},
			goiMAP.CapIMAP4rev2: {},
		},
	})

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("startIMAPServer: listen: %v", err)
	}
	go func() { _ = srv.Serve(ln) }()

	return ln.Addr().String(), u, func() {
		_ = srv.Close()
		_ = ln.Close()
	}
}

// appendMsg appends a raw RFC822 message via a fresh low-level connection.
func appendMsg(t *testing.T, imapAddr, mailbox, rawMsg string) goiMAP.UID {
	t.Helper()

	conn, err := net.Dial("tcp", imapAddr)
	if err != nil {
		t.Fatalf("appendMsg: dial: %v", err)
	}
	raw := imapclient.New(conn, &imapclient.Options{})
	defer raw.Close()

	if err := raw.Login(itUser, itPass).Wait(); err != nil {
		t.Fatalf("appendMsg: login: %v", err)
	}

	cmd := raw.Append(mailbox, int64(len(rawMsg)), nil)
	if _, err := cmd.Write([]byte(rawMsg)); err != nil {
		t.Fatalf("appendMsg: write: %v", err)
	}
	if err := cmd.Close(); err != nil {
		t.Fatalf("appendMsg: close: %v", err)
	}
	data, err := cmd.Wait()
	if err != nil {
		t.Fatalf("appendMsg: wait: %v", err)
	}
	return data.UID
}

// ============================================================================
// OAuth2 mock admin-api server
// ============================================================================

func startOAuth2MockServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", 405)
			return
		}
		resp := map[string]interface{}{
			"access_token": fmt.Sprintf("mock_at_%d", time.Now().UnixNano()),
			"expires_at":   time.Now().Add(10 * time.Minute).Format(time.RFC3339),
		}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			t.Errorf("oauth2 mock: encode: %v", err)
		}
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// ============================================================================
// capturingAuditEmitter
// ============================================================================

type itAuditEmitter struct {
	events []handlers.AuditEvent
}

func (e *itAuditEmitter) Emit(_ context.Context, ev handlers.AuditEvent) error {
	e.events = append(e.events, ev)
	return nil
}

func (e *itAuditEmitter) hasEvent(eventType string) bool {
	for _, ev := range e.events {
		if ev.EventType == eventType {
			return true
		}
	}
	return false
}

func (e *itAuditEmitter) count() int { return len(e.events) }

// ============================================================================
// directIMAPPool — a PoolGetter that uses real cleartext imapclient connections
// to the in-process IMAP test server (bypasses TLS).
// ============================================================================

type directIMAPPool struct {
	imapAddr string
	client   *imapwrap.Client // the currently active client (released on Release)
}

func newDirectIMAPPool(t *testing.T, imapAddr string) *directIMAPPool {
	t.Helper()
	return &directIMAPPool{imapAddr: imapAddr}
}

func (p *directIMAPPool) Get(_ context.Context, _ pool.ServiceConfig) (*imapwrap.Client, error) {
	conn, err := net.Dial("tcp", p.imapAddr)
	if err != nil {
		return nil, fmt.Errorf("directIMAPPool.Get: dial: %w", err)
	}
	creds := imapwrap.Credentials{
		Username: itUser,
		Password: itPass,
		AuthMode: imapwrap.AuthModeLogin,
	}
	c, err := imapwrap.DialFromConn(conn, creds)
	if err != nil {
		return nil, fmt.Errorf("directIMAPPool.Get: DialFromConn: %w", err)
	}
	p.client = c
	return c, nil
}

func (p *directIMAPPool) Release(_ pool.ServiceConfig, c *imapwrap.Client) {
	if c != nil {
		_ = c.Close()
	}
}

// ============================================================================
// Vault + OAuth2 stubs for integration tests
// ============================================================================

// itVaultStub returns a password-scheme credential pointing at the test IMAP server.
type itVaultStub struct{ imapAddr string }

func (v *itVaultStub) GetCredential(_ context.Context, _, _ string, _ vault.AuthScheme) (*vault.Credential, error) {
	payload := fmt.Sprintf(`{"username":%q,"password":%q,"imap_host":%q}`, itUser, itPass, v.imapAddr)
	return &vault.Credential{
		Value:      []byte(payload),
		AuthScheme: vault.AuthSchemeEmailPassword,
		BaseUrl:    v.imapAddr,
	}, nil
}

// itOAuth2VaultGetter satisfies oauth2.VaultCredentialGetter (for Manager).
type itOAuth2VaultGetter struct{}

func (v *itOAuth2VaultGetter) GetRefreshToken(_ context.Context, _, _ string) (string, string, error) {
	return "gmail", "rt_test_refresh_token_integration", nil
}

// itSMTPStub captures SMTP send calls.
type itSMTPStub struct {
	msgID string
	calls int
	last  smtp.EmailSendRequest
	err   error
}

func (s *itSMTPStub) Send(_ context.Context, _ smtp.Credential, req smtp.EmailSendRequest) (string, error) {
	if s.err != nil {
		return "", s.err
	}
	s.calls++
	s.last = req
	return s.msgID, nil
}

// ============================================================================
// itEnv bundles the full integration environment.
// ============================================================================

type itEnv struct {
	imapAddr string
	ae       *itAuditEmitter
	hdlr     *handlers.EmailHandlers
	smtp     *itSMTPStub
	claims   *authpkg.Claims
}

func newItEnv(t *testing.T) *itEnv {
	t.Helper()

	imapAddr, _, cleanup := startIMAPServer(t)
	t.Cleanup(cleanup)

	oauth2Srv := startOAuth2MockServer(t)

	ae := &itAuditEmitter{}
	smtpStub := &itSMTPStub{msgID: "it_msg_001"}

	vaultStub := &itVaultStub{imapAddr: imapAddr}
	oauth2Mgr := oauth2.NewManager(oauth2Srv.URL, &itOAuth2VaultGetter{}, "it_svc_token")

	imapPool := newDirectIMAPPool(t, imapAddr)

	rl := security.NewRateLimiter()
	hdlr := handlers.New(imapPool, oauth2Mgr, vaultStub, smtpStub, rl, ae)

	claims := &authpkg.Claims{
		Subject:   itAgentID,
		TenantID:  itTenantID,
		ServiceID: itServiceID,
		ExpiresAt: time.Now().Add(10 * time.Minute),
		IssuedAt:  time.Now(),
		Scopes:    []string{"read:email", "send:email", "write:email", "delete:email"},
	}

	return &itEnv{
		imapAddr: imapAddr,
		ae:       ae,
		hdlr:     hdlr,
		smtp:     smtpStub,
		claims:   claims,
	}
}

func (e *itEnv) injectClaims(r *http.Request) *http.Request {
	return r.WithContext(context.WithValue(r.Context(), handlers.ClaimsContextKey, e.claims))
}

// ============================================================================
// Integration test 1: ListMailboxes happy path
// ============================================================================

// TestInteg_ListMailboxes_HappyPath exercises the full list_mailboxes path:
// vault → IMAP connect → LIST → 200 response + audit event.
func TestInteg_ListMailboxes_HappyPath(t *testing.T) {
	env := newItEnv(t)

	req := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/v1/email-proxy/mailboxes?service_id=%s", itServiceID),
		nil)
	req = env.injectClaims(req)
	rr := httptest.NewRecorder()

	env.hdlr.HandleListMailboxes(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d; body: %s", rr.Code, rr.Body.String())
	}

	var resp struct {
		Mailboxes []struct {
			Name string `json:"name"`
		} `json:"mailboxes"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(resp.Mailboxes) == 0 {
		t.Error("expected at least one mailbox (INBOX), got none")
	}

	var names []string
	for _, m := range resp.Mailboxes {
		names = append(names, m.Name)
	}
	found := false
	for _, n := range names {
		if n == itInbox {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("INBOX not found in mailboxes: %v", names)
	}

	// Audit event must have been emitted.
	if !env.ae.hasEvent("email.mailboxes.listed") {
		t.Errorf("expected audit event email.mailboxes.listed, got: %v", env.ae.events)
	}
}

// ============================================================================
// Integration test 2: ListMessages happy path (INBOX pre-populated)
// ============================================================================

// TestInteg_ListMessages_HappyPath pre-appends one message to INBOX and then
// verifies HandleListMessages returns it with correct subject.
func TestInteg_ListMessages_HappyPath(t *testing.T) {
	env := newItEnv(t)

	// Pre-populate INBOX with one message.
	uid := appendMsg(t, env.imapAddr, itInbox, itRawMsg)
	if uid == 0 {
		t.Fatal("appendMsg returned UID 0")
	}

	req := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/v1/email-proxy/messages?service_id=%s&mailbox=%s&limit=10", itServiceID, itInbox),
		nil)
	req = env.injectClaims(req)
	rr := httptest.NewRecorder()

	env.hdlr.HandleListMessages(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d; body: %s", rr.Code, rr.Body.String())
	}

	var resp struct {
		Messages []struct {
			MessageID string `json:"message_id"`
			Subject   string `json:"subject"`
		} `json:"messages"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(resp.Messages) == 0 {
		t.Fatal("expected at least 1 message, got none")
	}
	if resp.Messages[0].Subject != "Integration Test" {
		t.Errorf("subject = %q, want %q", resp.Messages[0].Subject, "Integration Test")
	}

	// Audit event.
	if !env.ae.hasEvent("email.messages.listed") {
		t.Errorf("expected audit event email.messages.listed, got: %v", env.ae.events)
	}
}

// ============================================================================
// Integration test 3: SendMessage happy path
// ============================================================================

// TestInteg_SendMessage_HappyPath verifies HandleSendMessage reaches the SMTP
// stub and emits the correct audit event.
func TestInteg_SendMessage_HappyPath(t *testing.T) {
	env := newItEnv(t)

	body := `{"to":["bob@example.com"],"subject":"Integration Send","body":"hello from integration test"}`
	req := httptest.NewRequest(http.MethodPost,
		fmt.Sprintf("/v1/email-proxy/messages?service_id=%s", itServiceID),
		strings.NewReader(body))
	req = env.injectClaims(req)
	rr := httptest.NewRecorder()

	env.hdlr.HandleSendMessage(rr, req)

	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d; body: %s", rr.Code, rr.Body.String())
	}

	var resp map[string]string
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp["message_id"] != "it_msg_001" {
		t.Errorf("message_id = %q, want it_msg_001", resp["message_id"])
	}

	// Verify SMTP stub received the request.
	if env.smtp.calls != 1 {
		t.Errorf("SMTP Send calls = %d, want 1", env.smtp.calls)
	}
	if env.smtp.last.Subject != "Integration Send" {
		t.Errorf("SMTP subject = %q, want %q", env.smtp.last.Subject, "Integration Send")
	}

	// Verify audit event.
	if !env.ae.hasEvent("email.message.sent") {
		t.Errorf("expected audit event email.message.sent, got: %v", env.ae.events)
	}
}

// ============================================================================
// Integration test 4: SendMessage body not in audit payload
// ============================================================================

// TestInteg_SendMessage_AuditPayload_NoBodyLeak verifies that the email body
// never appears in the emitted audit event payload.
func TestInteg_SendMessage_AuditPayload_NoBodyLeak(t *testing.T) {
	env := newItEnv(t)

	const sensitiveBody = "INTEGRATION-SENSITIVE-BODY-CONTENT-12345"
	reqBody := fmt.Sprintf(`{"to":["bob@example.com"],"subject":"Leak Test","body":%q}`, sensitiveBody)
	req := httptest.NewRequest(http.MethodPost,
		fmt.Sprintf("/v1/email-proxy/messages?service_id=%s", itServiceID),
		strings.NewReader(reqBody))
	req = env.injectClaims(req)
	rr := httptest.NewRecorder()

	env.hdlr.HandleSendMessage(rr, req)

	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d; body: %s", rr.Code, rr.Body.String())
	}

	// Check no audit payload contains the sensitive body.
	for i, ev := range env.ae.events {
		b, _ := json.Marshal(ev.Payload)
		if strings.Contains(string(b), sensitiveBody) {
			t.Errorf("audit event[%d] payload contains sensitive body: %s", i, string(b))
		}
	}
}

// ============================================================================
// Integration test 5: Metrics counters incremented
// ============================================================================

// TestInteg_Metrics_AuditCounterIncremented verifies that audit events are
// counted — we use the capturing emitter and confirm event count increases.
func TestInteg_Metrics_AuditCounterIncremented(t *testing.T) {
	env := newItEnv(t)

	initialCount := env.ae.count()

	// Fire list_mailboxes
	req := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/v1/email-proxy/mailboxes?service_id=%s", itServiceID),
		nil)
	req = env.injectClaims(req)
	rr := httptest.NewRecorder()
	env.hdlr.HandleListMailboxes(rr, req)

	if env.ae.count() <= initialCount {
		t.Errorf("audit event count did not increase after list_mailboxes: before=%d after=%d",
			initialCount, env.ae.count())
	}
}

// ============================================================================
// Integration test 6: OAuth2 revoked token → 401
// ============================================================================

// TestInteg_OAuth2Revoked_Returns401 verifies that when the OAuth2 mock returns
// 401, the handler returns 401 to the caller.
func TestInteg_OAuth2Revoked_Returns401(t *testing.T) {
	// Start an OAuth2 mock that always returns 401
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/internal/oauth2/", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = io.WriteString(w, `{"mintkey:code":"oauth2_token_expired"}`)
	})
	revoked401Srv := httptest.NewServer(mux)
	t.Cleanup(revoked401Srv.Close)

	imapAddr, _, cleanup := startIMAPServer(t)
	t.Cleanup(cleanup)

	ae := &itAuditEmitter{}

	// Use OAuth2 vault credential so the oauth2 manager is invoked.
	vaultStub := &itOAuth2VaultStub{
		imapAddr: imapAddr,
		token:    "rt_revoked_integration",
	}
	oauth2Mgr := oauth2.NewManager(revoked401Srv.URL, &itOAuth2VaultGetter{}, "svc_token")

	imapPool := newDirectIMAPPool(t, imapAddr)
	rl := security.NewRateLimiter()
	smtpStub := &itSMTPStub{msgID: "x"}
	hdlr := handlers.New(imapPool, oauth2Mgr, vaultStub, smtpStub, rl, ae)

	claims := &authpkg.Claims{
		Subject:   itAgentID,
		TenantID:  itTenantID,
		ServiceID: itServiceID,
		ExpiresAt: time.Now().Add(10 * time.Minute),
		IssuedAt:  time.Now(),
		Scopes:    []string{"send:email"},
	}

	reqBody := `{"to":["bob@example.com"],"subject":"revoked test","body":"hi"}`
	req := httptest.NewRequest(http.MethodPost,
		fmt.Sprintf("/v1/email-proxy/messages?service_id=%s", itServiceID),
		strings.NewReader(reqBody))
	req = req.WithContext(context.WithValue(req.Context(), handlers.ClaimsContextKey, claims))
	rr := httptest.NewRecorder()

	hdlr.HandleSendMessage(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 on revoked token, got %d; body: %s", rr.Code, rr.Body.String())
	}
}

// itOAuth2VaultStub returns an OAuth2 credential (triggers oauth2.Manager path).
type itOAuth2VaultStub struct {
	imapAddr string
	token    string
}

func (v *itOAuth2VaultStub) GetCredential(_ context.Context, _, _ string, _ vault.AuthScheme) (*vault.Credential, error) {
	payload := fmt.Sprintf(`{"provider":"gmail","refresh_token":%q,"email_address":"alice@example.com"}`, v.token)
	return &vault.Credential{
		Value:      []byte(payload),
		AuthScheme: vault.AuthSchemeEmailOAuth2,
		BaseUrl:    v.imapAddr,
	}, nil
}

// ============================================================================
// Integration test 7: ScrubBodyForLog end-to-end
// ============================================================================

// TestInteg_ScrubBodyForLog_ShapeAndNoContent verifies the scrub function used
// in audit payloads throughout all handlers.
func TestInteg_ScrubBodyForLog_ShapeAndNoContent(t *testing.T) {
	cases := []struct {
		input    string
		wantZero bool
	}{
		{"", true},
		{"single line no newline", false},
		{"line1\nline2\nline3", false},
		{"SENSITIVE_CONTENT_DO_NOT_LOG: secret123", false},
	}

	for _, tc := range cases {
		out := security.ScrubBodyForLog(tc.input)
		if strings.Contains(out, tc.input) && tc.input != "" {
			t.Errorf("ScrubBodyForLog(%q) contains input: got %q", tc.input, out)
		}
		if tc.wantZero {
			if out != "<scrubbed:0 bytes,0 lines>" {
				t.Errorf("ScrubBodyForLog(%q): want zero summary, got %q", tc.input, out)
			}
		} else {
			if !strings.HasPrefix(out, "<scrubbed:") {
				t.Errorf("ScrubBodyForLog(%q): want <scrubbed:...> prefix, got %q", tc.input, out)
			}
		}
	}
}

// ============================================================================
// Integration test 8: Multiple audit events across handlers
// ============================================================================

// TestInteg_MultipleHandlers_AuditEventsEmitted verifies that back-to-back
// calls to list_mailboxes and send_message each emit distinct audit events.
func TestInteg_MultipleHandlers_AuditEventsEmitted(t *testing.T) {
	env := newItEnv(t)

	// Call 1: list_mailboxes
	req1 := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/v1/email-proxy/mailboxes?service_id=%s", itServiceID),
		nil)
	req1 = env.injectClaims(req1)
	rr1 := httptest.NewRecorder()
	env.hdlr.HandleListMailboxes(rr1, req1)

	// Call 2: send_message
	sendBody := `{"to":["bob@example.com"],"subject":"Multi handler","body":"hello"}`
	req2 := httptest.NewRequest(http.MethodPost,
		fmt.Sprintf("/v1/email-proxy/messages?service_id=%s", itServiceID),
		strings.NewReader(sendBody))
	req2 = env.injectClaims(req2)
	rr2 := httptest.NewRecorder()
	env.hdlr.HandleSendMessage(rr2, req2)

	if !env.ae.hasEvent("email.mailboxes.listed") {
		t.Errorf("expected email.mailboxes.listed event")
	}
	if !env.ae.hasEvent("email.message.sent") {
		t.Errorf("expected email.message.sent event")
	}
	if env.ae.count() < 2 {
		t.Errorf("expected at least 2 audit events, got %d", env.ae.count())
	}
}

// ============================================================================
// Compile-time stub interface checks
// ============================================================================

var (
	_ handlers.PoolGetter   = (*directIMAPPool)(nil)
	_ handlers.VaultGetter  = (*itVaultStub)(nil)
	_ handlers.VaultGetter  = (*itOAuth2VaultStub)(nil)
	_ handlers.SMTPSender   = (*itSMTPStub)(nil)
	_ handlers.AuditEmitter = (*itAuditEmitter)(nil)

	// Suppress unused import
	_ = bytes.NewBuffer
)
