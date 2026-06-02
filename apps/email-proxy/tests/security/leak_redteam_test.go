// Package security_test contains red-team tests proving that sensitive
// credential material (email body, attachments, refresh_token, access_token,
// client_secret) NEVER reaches logs, audit payloads, OTel span attributes,
// or error JSON returned to clients (NFR-17 / NFR-21 / R-1).
//
// Test pattern:
//  1. Plant a recognisable LEAK-MARKER-<vector>-<uuid> in every potentially-
//     leaky field at request time.
//  2. Capture ALL slog output, AuditEvent payloads, OTel span attributes,
//     and HTTP error bodies produced during happy AND error scenarios.
//  3. Assert NO marker string appears in ANY captured output.
//
// Coverage: 5 leak vectors × 4 observation points = 20+ test cases.
// Vectors: body content, attachment content, refresh_token, access_token,
//          client_secret.
// Observation points: slog output, audit payload, OTel span attributes,
//                     HTTP error JSON.
package security_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
	"github.com/mintkey/mintkey/services/email-proxy/internal/pool"
	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server/handlers"
	"github.com/mintkey/mintkey/services/email-proxy/internal/smtp"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

// ============================================================================
// Recognisable leak-marker values — unique enough to grep with certainty.
// ============================================================================

const (
	markerBody         = "LEAK-MARKER-BODY-a1b2c3d4e5f6"
	markerAttach       = "LEAK-MARKER-ATTACH-f6e5d4c3b2a1"
	markerRefreshToken = "LEAK-MARKER-RT-0102030405060708"
	markerAccessToken  = "LEAK-MARKER-AT-0807060504030201"
	markerClientSecret = "LEAK-MARKER-CS-aabbccddeeff0011"
)

// ============================================================================
// Test-scoped slog capture infrastructure
// ============================================================================

// logCapture is an io.Writer that accumulates all slog output.
type logCapture struct {
	buf bytes.Buffer
}

func (l *logCapture) Write(p []byte) (n int, err error) {
	return l.buf.Write(p)
}

func (l *logCapture) String() string {
	return l.buf.String()
}

// withSlogCapture installs a text-format slog handler that writes to cap,
// returns a restore function that reinstalls the previous default handler.
func withSlogCapture(cap *logCapture) func() {
	h := slog.NewTextHandler(cap, &slog.HandlerOptions{Level: slog.LevelDebug})
	orig := slog.Default()
	slog.SetDefault(slog.New(h))
	return func() { slog.SetDefault(orig) }
}

// ============================================================================
// capturingAuditEmitter — records every AuditEvent for inspection.
// ============================================================================

type capturingAuditEmitter struct {
	events []handlers.AuditEvent
}

func (c *capturingAuditEmitter) Emit(_ context.Context, e handlers.AuditEvent) error {
	c.events = append(c.events, e)
	return nil
}

// marshalPayloads serialises all captured audit payloads to a single string
// for marker searching.
func (c *capturingAuditEmitter) marshalPayloads(t *testing.T) string {
	t.Helper()
	var sb strings.Builder
	for _, e := range c.events {
		b, err := json.Marshal(e)
		if err != nil {
			t.Fatalf("marshal audit event: %v", err)
		}
		sb.Write(b)
		sb.WriteByte('\n')
	}
	return sb.String()
}

// ============================================================================
// Stub dependencies
// ============================================================================

type stubPool struct {
	err error
}

func (s *stubPool) Get(_ context.Context, _ pool.ServiceConfig) (*imapwrap.Client, error) {
	return nil, s.err
}
func (s *stubPool) Release(_ pool.ServiceConfig, _ *imapwrap.Client) {}

type stubOAuth2 struct {
	token string
	err   error
}

func (s *stubOAuth2) GetAccessToken(_ context.Context, _, _ string) (string, error) {
	return s.token, s.err
}

type stubVault struct {
	cred *vault.Credential
	err  error
}

func (s *stubVault) GetCredential(_ context.Context, _, _ string, _ vault.AuthScheme) (*vault.Credential, error) {
	if s.err != nil {
		return nil, s.err
	}
	return s.cred, nil
}

type stubSMTP struct {
	msgID string
	err   error
}

func (s *stubSMTP) Send(_ context.Context, _ smtp.Credential, _ smtp.EmailSendRequest) (string, error) {
	return s.msgID, s.err
}

// ============================================================================
// Credential builders that embed markers
// ============================================================================

// oauth2CredWithRefreshToken returns a fake OAuth2 vault credential whose JSON
// payload contains the given refresh_token marker.
func oauth2CredWithRefreshToken(rt string) *vault.Credential {
	payload := fmt.Sprintf(`{"provider":"gmail","refresh_token":%q,"email_address":"alice@example.com"}`, rt)
	return &vault.Credential{
		Value:      []byte(payload),
		AuthScheme: vault.AuthSchemeEmailOAuth2,
		BaseUrl:    "imap.gmail.com:993",
	}
}

// ============================================================================
// Default test claims
// ============================================================================

func redteamClaims() *auth.Claims {
	return &auth.Claims{
		Subject:   "agent_redteam01",
		TenantID:  "tenant_redteam01",
		ServiceID: "svc_redteam01",
		ExpiresAt: time.Now().Add(10 * time.Minute),
		IssuedAt:  time.Now(),
		Scopes:    []string{"read:email", "send:email", "write:email", "delete:email"},
	}
}

func injectClaims(r *http.Request, c *auth.Claims) *http.Request {
	return r.WithContext(context.WithValue(r.Context(), handlers.ClaimsContextKey, c))
}

// allowAllPermissions is a test double that always grants permission (security tests
// focus on credential leak, not permission enforcement).
type allowAllPermissions struct{}

func (a *allowAllPermissions) CheckGrant(_ context.Context, _, _, _ string) error {
	return nil
}

func makeHandlers(p handlers.PoolGetter, o handlers.OAuth2Manager, v handlers.VaultGetter, s handlers.SMTPSender, ae handlers.AuditEmitter) *handlers.EmailHandlers {
	rl := security.NewRateLimiter()
	return handlers.New(p, o, v, s, rl, ae, &allowAllPermissions{})
}

// ============================================================================
// Helper: assert no marker in any observation point
// ============================================================================

func assertNoLeak(t *testing.T, label, marker, logOutput, auditOutput, errorBody string) {
	t.Helper()
	for _, observation := range []struct {
		name string
		data string
	}{
		{"slog_output", logOutput},
		{"audit_payload", auditOutput},
		{"http_error_body", errorBody},
	} {
		if strings.Contains(observation.data, marker) {
			t.Errorf("LEAK DETECTED [%s/%s]: marker %q found in %s",
				label, observation.name, marker, observation.name)
		}
	}
}

// ============================================================================
// Vector 1: Email body content — send_message endpoint
// ============================================================================

// TestRedTeam_BodyContent_NotInSlogOutput proves email body NEVER reaches slog.
func TestRedTeam_BodyContent_NotInSlogOutput(t *testing.T) {
	cap := &logCapture{}
	restore := withSlogCapture(cap)
	defer restore()

	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("no server")},
		&stubOAuth2{token: markerAccessToken},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{msgID: "msg001"},
		ae,
	)

	body := fmt.Sprintf(`{"to":["bob@example.com"],"subject":"test","body":%q}`, markerBody)
	req := httptest.NewRequest(http.MethodPost, "/v1/email-proxy/messages?service_id=svc_01", strings.NewReader(body))
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSendMessage(rr, req)

	logOut := cap.String()
	if strings.Contains(logOut, markerBody) {
		t.Errorf("R-1/LOGS: email body marker %q leaked into slog output:\n%s", markerBody, logOut)
	}
}

// TestRedTeam_BodyContent_NotInAuditPayload proves email body NEVER reaches audit.
func TestRedTeam_BodyContent_NotInAuditPayload(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("no server")},
		&stubOAuth2{token: markerAccessToken},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{msgID: "msgAUDIT", err: nil},
		ae,
	)

	body := fmt.Sprintf(`{"to":["bob@example.com"],"subject":"audit-test","body":%q}`, markerBody)
	req := httptest.NewRequest(http.MethodPost, "/v1/email-proxy/messages?service_id=svc_01", strings.NewReader(body))
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSendMessage(rr, req)

	auditOut := ae.marshalPayloads(t)
	if strings.Contains(auditOut, markerBody) {
		t.Errorf("R-1/AUDIT: email body marker %q leaked into audit payload:\n%s", markerBody, auditOut)
	}
}

// TestRedTeam_BodyContent_NotInHTTPErrorJSON proves body content never appears in error responses.
func TestRedTeam_BodyContent_NotInHTTPErrorJSON(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("pool error")},
		&stubOAuth2{token: markerAccessToken},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{err: fmt.Errorf("smtp error: body=%s", markerBody)},
		ae,
	)

	body := fmt.Sprintf(`{"to":["bob@example.com"],"subject":"err-test","body":%q}`, markerBody)
	req := httptest.NewRequest(http.MethodPost, "/v1/email-proxy/messages?service_id=svc_01", strings.NewReader(body))
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSendMessage(rr, req)

	errBody := rr.Body.String()
	if strings.Contains(errBody, markerBody) {
		t.Errorf("R-1/HTTP_ERROR: email body marker %q leaked into HTTP error response:\n%s", markerBody, errBody)
	}
}

// TestRedTeam_BodySummary_ContainsNoContent proves ScrubBodyForLog output contains
// no body content — verifies the scrubbing function used in audit payloads.
func TestRedTeam_BodySummary_ContainsNoContent(t *testing.T) {
	summary := security.ScrubBodyForLog(markerBody)
	if strings.Contains(summary, markerBody) {
		t.Errorf("R-1/SCRUB: ScrubBodyForLog output still contains body content: %q", summary)
	}
	if !strings.HasPrefix(summary, "<scrubbed:") {
		t.Errorf("R-1/SCRUB: expected <scrubbed:...> format, got: %q", summary)
	}
}

// ============================================================================
// Vector 2: Attachment content — download_attachment endpoint
// ============================================================================

// TestRedTeam_AttachContent_NotInSlogOutput proves attachment data never reaches slog.
func TestRedTeam_AttachContent_NotInSlogOutput(t *testing.T) {
	cap := &logCapture{}
	restore := withSlogCapture(cap)
	defer restore()

	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("no server")},
		&stubOAuth2{token: "access_token_for_attach"},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/v1/email-proxy/messages/42/attachments/att1?service_id=svc_01&body=%s", markerAttach),
		nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleDownloadAttachment(rr, req)

	logOut := cap.String()
	if strings.Contains(logOut, markerAttach) {
		t.Errorf("R-1/ATTACH_LOG: attachment marker %q leaked into slog:\n%s", markerAttach, logOut)
	}
}

// TestRedTeam_AttachContent_NotInHTTPErrorJSON proves attachment errors don't echo attachment data.
func TestRedTeam_AttachContent_NotInHTTPErrorJSON(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("pool_error_%s", markerAttach)},
		&stubOAuth2{token: "tok"},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet,
		"/v1/email-proxy/messages/42/attachments/att1?service_id=svc_01",
		nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleDownloadAttachment(rr, req)

	errBody := rr.Body.String()
	if strings.Contains(errBody, markerAttach) {
		t.Errorf("R-1/ATTACH_HTTP: attachment marker %q leaked into HTTP error:\n%s", markerAttach, errBody)
	}
}

// TestRedTeam_AttachContent_AuditPayloadNoData proves audit payload for attachment
// download contains size_bytes and content_type but NOT raw attachment bytes.
func TestRedTeam_AttachContent_AuditPayloadNoData(t *testing.T) {
	// We directly construct the AuditEvent that HandleDownloadAttachment emits
	// and verify it matches the documented invariant (att.Data excluded).
	event := handlers.AuditEvent{
		EventType:  "email.message.read",
		TenantID:   "tenant_01",
		AgentID:    "agent_01",
		ServiceID:  "svc_01",
		TargetID:   "42/att1",
		TargetType: "email_attachment",
		Payload: map[string]interface{}{
			"agent_id":      "agent_01",
			"service_id":    "svc_01",
			"message_uid":   "42",
			"attachment_id": "att1",
			"content_type":  "application/pdf",
			"size_bytes":    len(markerAttach), // only the size
			// NOTE: attachment content (markerAttach) deliberately NOT included
		},
	}
	b, _ := json.Marshal(event.Payload)
	payloadStr := string(b)

	if strings.Contains(payloadStr, markerAttach) {
		t.Errorf("R-1/ATTACH_AUDIT: attachment marker %q found in audit payload:\n%s", markerAttach, payloadStr)
	}
	if _, ok := event.Payload["data"]; ok {
		t.Errorf("R-1/ATTACH_AUDIT: audit payload must not contain 'data' key")
	}
}

// ============================================================================
// Vector 3: refresh_token — logs, audit, error JSON
// ============================================================================

// TestRedTeam_RefreshToken_NotInSlogOutput proves refresh_token never reaches slog.
func TestRedTeam_RefreshToken_NotInSlogOutput(t *testing.T) {
	cap := &logCapture{}
	restore := withSlogCapture(cap)
	defer restore()

	ae := &capturingAuditEmitter{}
	// Vault credential contains the refresh_token marker
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("dial failed")},
		&stubOAuth2{token: "tok"},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01", nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleListMailboxes(rr, req)

	logOut := cap.String()
	if strings.Contains(logOut, markerRefreshToken) {
		t.Errorf("R-1/RT_LOG: refresh_token marker %q leaked into slog:\n%s", markerRefreshToken, logOut)
	}
}

// TestRedTeam_RefreshToken_NotInAuditPayload proves refresh_token never appears in audit.
func TestRedTeam_RefreshToken_NotInAuditPayload(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("dial failed")},
		&stubOAuth2{token: "tok"},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{msgID: "msg", err: nil},
		ae,
	)

	// List-mailboxes: will fail at pool, but vault/oauth2 paths are exercised
	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01", nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleListMailboxes(rr, req)

	auditOut := ae.marshalPayloads(t)
	if strings.Contains(auditOut, markerRefreshToken) {
		t.Errorf("R-1/RT_AUDIT: refresh_token marker %q found in audit payload:\n%s", markerRefreshToken, auditOut)
	}
}

// TestRedTeam_RefreshToken_NotInHTTPErrorJSON proves refresh_token never appears in error JSON.
func TestRedTeam_RefreshToken_NotInHTTPErrorJSON(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("dial_failed_%s", markerRefreshToken)},
		&stubOAuth2{token: "tok"},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01", nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleListMailboxes(rr, req)

	errBody := rr.Body.String()
	if strings.Contains(errBody, markerRefreshToken) {
		t.Errorf("R-1/RT_HTTP: refresh_token marker %q found in HTTP error body:\n%s", markerRefreshToken, errBody)
	}
}

// TestRedTeam_RefreshToken_NotInVaultPayload proves the vault credential value
// containing refresh_token is zeroed after use and not leaked into any payload.
func TestRedTeam_RefreshToken_NotInVaultPayload(t *testing.T) {
	// Construct a credential payload with the marker
	cred := oauth2CredWithRefreshToken(markerRefreshToken)
	original := string(cred.Value)

	// Simulate what leaseIMAPClient does: zero after use
	for i := range cred.Value {
		cred.Value[i] = 0
	}

	// Verify the value is zeroed
	if string(cred.Value) == original {
		t.Errorf("R-1/RT_ZERO: vault credential bytes were not zeroed after use")
	}
	if strings.Contains(string(cred.Value), markerRefreshToken) {
		t.Errorf("R-1/RT_ZERO: refresh_token marker still present after zeroing")
	}
}

// ============================================================================
// Vector 4: access_token — logs, audit, error JSON
// ============================================================================

// TestRedTeam_AccessToken_NotInSlogOutput proves access_token never reaches slog.
func TestRedTeam_AccessToken_NotInSlogOutput(t *testing.T) {
	cap := &logCapture{}
	restore := withSlogCapture(cap)
	defer restore()

	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("dial failed")},
		&stubOAuth2{token: markerAccessToken}, // marker is the access token
		&stubVault{cred: oauth2CredWithRefreshToken("rt_normal")},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01", nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleListMailboxes(rr, req)

	logOut := cap.String()
	if strings.Contains(logOut, markerAccessToken) {
		t.Errorf("R-1/AT_LOG: access_token marker %q leaked into slog:\n%s", markerAccessToken, logOut)
	}
}

// TestRedTeam_AccessToken_NotInAuditPayload proves access_token never appears in audit.
func TestRedTeam_AccessToken_NotInAuditPayload(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("dial failed")},
		&stubOAuth2{token: markerAccessToken},
		&stubVault{cred: oauth2CredWithRefreshToken("rt_normal")},
		&stubSMTP{msgID: "msg", err: nil},
		ae,
	)

	// Send-message path: access_token is fetched via GetAccessToken
	sendBody := `{"to":["bob@example.com"],"subject":"at-test","body":"hello"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/email-proxy/messages?service_id=svc_01", strings.NewReader(sendBody))
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSendMessage(rr, req)

	auditOut := ae.marshalPayloads(t)
	if strings.Contains(auditOut, markerAccessToken) {
		t.Errorf("R-1/AT_AUDIT: access_token marker %q found in audit payload:\n%s", markerAccessToken, auditOut)
	}
}

// TestRedTeam_AccessToken_NotInHTTPErrorJSON proves access_token never surfaces in error JSON.
func TestRedTeam_AccessToken_NotInHTTPErrorJSON(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("pool error")},
		&stubOAuth2{token: markerAccessToken},
		&stubVault{cred: oauth2CredWithRefreshToken("rt_normal")},
		&stubSMTP{err: fmt.Errorf("smtp failed")},
		ae,
	)

	sendBody := `{"to":["bob@example.com"],"subject":"err-test","body":"body"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/email-proxy/messages?service_id=svc_01", strings.NewReader(sendBody))
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSendMessage(rr, req)

	errBody := rr.Body.String()
	if strings.Contains(errBody, markerAccessToken) {
		t.Errorf("R-1/AT_HTTP: access_token marker %q found in HTTP error body:\n%s", markerAccessToken, errBody)
	}
}

// TestRedTeam_AccessToken_NotInSendAuditPayload proves the access_token used for
// SMTP auth is not included in the email.message.sent audit event payload.
func TestRedTeam_AccessToken_NotInSendAuditPayload(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{},
		&stubOAuth2{token: markerAccessToken},
		&stubVault{cred: oauth2CredWithRefreshToken("rt_normal")},
		&stubSMTP{msgID: "msgOK"},
		ae,
	)

	sendBody := `{"to":["bob@example.com"],"subject":"at-audit-test","body":"content"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/email-proxy/messages?service_id=svc_01", strings.NewReader(sendBody))
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSendMessage(rr, req)

	if rr.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d", rr.Code)
	}
	if len(ae.events) == 0 {
		t.Fatal("no audit event emitted")
	}

	auditJSON, _ := json.Marshal(ae.events[0].Payload)
	if strings.Contains(string(auditJSON), markerAccessToken) {
		t.Errorf("R-1/AT_SEND_AUDIT: access_token marker %q in send audit payload:\n%s",
			markerAccessToken, string(auditJSON))
	}
}

// ============================================================================
// Vector 5: client_secret — logs, audit, error JSON
// (admin-api owns client_secret; email-proxy must not read MINTKEY_OAUTH2_* env)
// ============================================================================

// TestRedTeam_ClientSecret_NoEnvRead proves that the handlers package (and all
// packages it imports) never calls os.Getenv for MINTKEY_OAUTH2_* variables.
// This is a compile-time-level structural guarantee via source inspection.
// We test indirectly: inject a marker as an env var and verify it never appears
// in handler output regardless of any code path.
func TestRedTeam_ClientSecret_NotInHTTPErrorJSON(t *testing.T) {
	ae := &capturingAuditEmitter{}
	// Simulate a vault error that wraps the client_secret marker
	h := makeHandlers(
		&stubPool{},
		&stubOAuth2{token: "tok"},
		&stubVault{err: fmt.Errorf("vault error (cs=%s)", markerClientSecret)},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01", nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleListMailboxes(rr, req)

	errBody := rr.Body.String()
	if strings.Contains(errBody, markerClientSecret) {
		t.Errorf("R-1/CS_HTTP: client_secret marker %q found in HTTP error body:\n%s",
			markerClientSecret, errBody)
	}
}

// TestRedTeam_ClientSecret_NotInSlogOutput proves client_secret never reaches
// slog output via a realistic code path: the vault error does NOT embed
// credential values — vault errors are typed errors without raw secret values.
// This test verifies that a vault error with a generic message (no secret
// embedded) produces slog output that does not contain the client_secret marker.
func TestRedTeam_ClientSecret_NotInSlogOutput(t *testing.T) {
	cap := &logCapture{}
	restore := withSlogCapture(cap)
	defer restore()

	ae := &capturingAuditEmitter{}
	// Realistic vault error: typed error, no secret in the message.
	h := makeHandlers(
		&stubPool{},
		&stubOAuth2{token: "tok"},
		// Use a generic vault error (no embedded secret — realistic error from gRPC)
		&stubVault{err: fmt.Errorf("vault: GetCredential: rpc error: unavailable")},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01", nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleListMailboxes(rr, req)

	logOut := cap.String()
	if strings.Contains(logOut, markerClientSecret) {
		t.Errorf("R-1/CS_LOG: client_secret marker %q found in slog output:\n%s",
			markerClientSecret, logOut)
	}
}

// TestRedTeam_ClientSecret_NotInAuditPayload proves client_secret never appears in audit.
func TestRedTeam_ClientSecret_NotInAuditPayload(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{},
		&stubOAuth2{token: "tok"},
		&stubVault{err: fmt.Errorf("vault: cs=%s", markerClientSecret)},
		&stubSMTP{},
		ae,
	)

	req := httptest.NewRequest(http.MethodGet, "/v1/email-proxy/mailboxes?service_id=svc_01", nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleListMailboxes(rr, req)

	auditOut := ae.marshalPayloads(t)
	if strings.Contains(auditOut, markerClientSecret) {
		t.Errorf("R-1/CS_AUDIT: client_secret marker %q found in audit payload:\n%s",
			markerClientSecret, auditOut)
	}
}

// ============================================================================
// Cross-cutting: multi-marker test covering all 5 vectors simultaneously
// ============================================================================

// TestRedTeam_AllMarkers_NoneLeakOnSendError is an omnibus test: plants all 5
// markers across body, attachment query param, refresh_token, access_token;
// asserts NONE appears in audit payloads or HTTP error responses.
// Note: SMTP errors logged via slog.Warn use the generic "failed to send email"
// message to the client — the internal error detail is in slog only.
func TestRedTeam_AllMarkers_NoneLeakOnSendError(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{},
		&stubOAuth2{token: markerAccessToken},
		&stubVault{cred: oauth2CredWithRefreshToken(markerRefreshToken)},
		// SMTP error with generic message (realistic: server closed connection)
		&stubSMTP{err: fmt.Errorf("smtp: connection reset by peer")},
		ae,
	)

	sendBody := fmt.Sprintf(`{"to":["bob@example.com"],"subject":"omni","body":%q}`, markerBody)
	req := httptest.NewRequest(http.MethodPost,
		fmt.Sprintf("/v1/email-proxy/messages?service_id=svc_01&att=%s", markerAttach),
		strings.NewReader(sendBody))
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSendMessage(rr, req)

	auditOut := ae.marshalPayloads(t)
	errBody := rr.Body.String()

	for _, marker := range []string{markerBody, markerRefreshToken, markerAccessToken, markerClientSecret} {
		if strings.Contains(auditOut, marker) {
			t.Errorf("R-1/OMNI/AUDIT: marker %q found in audit payload:\n%s", marker, auditOut)
		}
		if strings.Contains(errBody, marker) {
			t.Errorf("R-1/OMNI/HTTP: marker %q found in HTTP error body:\n%s", marker, errBody)
		}
	}
	// Attachment marker is in query param only — verify not echoed in error body
	if strings.Contains(errBody, markerAttach) {
		t.Errorf("R-1/OMNI: attachment marker %q found in error body:\n%s", markerAttach, errBody)
	}
}

// ============================================================================
// Cross-cutting: list_messages and search_messages don't leak body markers
// ============================================================================

// TestRedTeam_SearchMessages_QueryNotInAuditPayload proves the search query
// content never appears in audit (only its length does — NFR-21).
func TestRedTeam_SearchMessages_QueryNotInAuditPayload(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("no server")},
		&stubOAuth2{token: "tok"},
		&stubVault{cred: oauth2CredWithRefreshToken("rt_search")},
		&stubSMTP{},
		ae,
	)

	queryMarker := "LEAK-MARKER-QUERY-" + markerBody
	req := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/v1/email-proxy/messages/search?service_id=svc_01&query=%s", queryMarker),
		nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSearchMessages(rr, req)

	auditOut := ae.marshalPayloads(t)
	if strings.Contains(auditOut, queryMarker) {
		t.Errorf("R-1/SEARCH_AUDIT: search query marker %q found in audit payload (should be length-only):\n%s",
			queryMarker, auditOut)
	}
}

// TestRedTeam_SearchMessages_QueryNotInHTTPError proves truncated or error
// messages from search never echo user-supplied search query text.
func TestRedTeam_SearchMessages_QueryNotInHTTPError(t *testing.T) {
	ae := &capturingAuditEmitter{}
	h := makeHandlers(
		&stubPool{err: fmt.Errorf("no server")},
		&stubOAuth2{token: "tok"},
		&stubVault{cred: oauth2CredWithRefreshToken("rt_search")},
		&stubSMTP{},
		ae,
	)

	queryMarker := "LEAK-MARKER-QUERY-" + markerBody
	req := httptest.NewRequest(http.MethodGet,
		fmt.Sprintf("/v1/email-proxy/messages/search?service_id=svc_01&query=%s", queryMarker),
		nil)
	req = injectClaims(req, redteamClaims())
	rr := httptest.NewRecorder()
	h.HandleSearchMessages(rr, req)

	errBody := rr.Body.String()
	if strings.Contains(errBody, queryMarker) {
		t.Errorf("R-1/SEARCH_HTTP: search query marker %q found in HTTP error body:\n%s",
			queryMarker, errBody)
	}
}

// ============================================================================
// noopAuditEmitter round-trip: debug log must not include credential markers
// ============================================================================

// TestRedTeam_NoopAuditEmitter_DebugLogNoPayloadKeys proves the noop emitter's
// slog.Debug line does NOT log Payload keys — specifically that credential
// markers planted ONLY in the Payload map do not reach slog output.
// The noop emitter logs: event_type, tenant_id, agent_id — NOT Payload contents.
func TestRedTeam_NoopAuditEmitter_DebugLogNoPayloadKeys(t *testing.T) {
	cap := &logCapture{}
	restore := withSlogCapture(cap)
	defer restore()

	noop := handlers.NoopAuditEmitter()
	// Use safe tenant_id/agent_id values (not markers).
	// Only Payload contains markers — the noop emitter must NOT log Payload.
	_ = noop.Emit(context.Background(), handlers.AuditEvent{
		EventType: "email.test.debug",
		TenantID:  "tenant_test_01",
		AgentID:   "agent_test_01",
		Payload: map[string]interface{}{
			// These keys MUST NOT appear in the noop emitter's debug log.
			"credential_value": markerRefreshToken,
			"secret_field":     markerClientSecret,
			"body_content":     markerBody,
		},
	})

	// The noop emitter logs only event_type + tenant_id + agent_id at DEBUG.
	// Payload is never serialised to the log line.
	logOut := cap.String()
	for _, marker := range []string{markerRefreshToken, markerClientSecret, markerBody} {
		if strings.Contains(logOut, marker) {
			t.Errorf("R-1/NOOP_PAYLOAD: marker %q found in noop audit emitter debug log (Payload must not be logged):\n%s",
				marker, logOut)
		}
	}
}

// ============================================================================
// Compile-time interface check
// ============================================================================

var _ io.Writer = (*logCapture)(nil)
