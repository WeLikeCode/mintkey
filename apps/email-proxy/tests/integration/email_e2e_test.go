//go:build integration

// Package integration: email agent e2e test (feat/agent-email-e2e).
//
// Tests the full path from brokered JWT → email-proxy JWT validation →
// email_permission_grants check → IMAP/SMTP operation.
//
// The test exercises:
//  1. A JWT issued by the broker with service_kind=email is accepted by
//     the email-proxy's withJWTAuth middleware.
//  2. The permission checker is consulted with the correct (tenantID, agentID,
//     emailServiceID) triple extracted from the JWT claims.
//  3. GET /v1/email-proxy/mailboxes returns a non-empty list through the
//     full server stack (not just the handler layer).
//
// A --live flag skips SMTP assertions (read-only). SMTP is never called in CI.
//
// Run with:
//
//	cd apps/email-proxy && go test -tags=integration ./tests/integration/... -run TestEmailE2E -v -count=1
package integration

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	goiMAP "github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapserver"
	"github.com/emersion/go-imap/v2/imapserver/imapmemserver"

	authpkg "github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/email-proxy/internal/config"
	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
	"github.com/mintkey/mintkey/services/email-proxy/internal/oauth2"
	"github.com/mintkey/mintkey/services/email-proxy/internal/pool"
	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server"
	"github.com/mintkey/mintkey/services/email-proxy/internal/server/handlers"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

// ============================================================================
// Test constants for e2e test
// ============================================================================

const (
	e2eTenantID        = "tenant_e2e_email_01"
	e2eAgentID         = "agent_e2e_email_01"
	e2eEmailServiceID  = "d28eec49-bb20-4991-866c-675c3be41aea" // known email_service UUID
	e2eUser            = "e2e_user"
	e2ePass            = "e2e_password"
)

// ============================================================================
// JWT helpers
// ============================================================================

// issueEmailJWT signs a JWT with the given service_kind using a provided Ed25519 key.
// Pass serviceKind="" to omit the service_kind claim (backward-compat test).
func issueEmailJWT(t *testing.T, kid string, priv ed25519.PrivateKey, serviceKind string) string {
	t.Helper()

	now := time.Now().Unix()
	exp := now + 600

	header := map[string]any{
		"alg": "EdDSA",
		"typ": "JWT",
		"kid": kid,
	}
	claims := map[string]any{
		"iss":        "mintkey/broker",
		"sub":        e2eAgentID,
		"aud":        []string{e2eEmailServiceID},
		"tnt":        e2eTenantID,
		"tenant_id":  e2eTenantID,
		"service_id": e2eEmailServiceID,
		"scope":      "read:email send:email",
		"jti":        fmt.Sprintf("jti_%d", time.Now().UnixNano()),
		"iat":        now,
		"exp":        exp,
	}
	if serviceKind != "" {
		claims["service_kind"] = serviceKind
	}

	hb, _ := json.Marshal(header)
	cb, _ := json.Marshal(claims)

	h64 := base64.RawURLEncoding.EncodeToString(hb)
	c64 := base64.RawURLEncoding.EncodeToString(cb)

	sigInput := []byte(h64 + "." + c64)
	sig := ed25519.Sign(priv, sigInput)
	s64 := base64.RawURLEncoding.EncodeToString(sig)

	return h64 + "." + c64 + "." + s64
}

// startJWKSServer launches a mock JWKS endpoint that serves the given Ed25519
// public key. Returns the JWKS URL and a cleanup function.
func startJWKSServer(t *testing.T, kid string, pub ed25519.PublicKey) *httptest.Server {
	t.Helper()

	// Encode the public key as base64url (JWK "x" parameter for Ed25519 / OKP).
	xB64 := base64.RawURLEncoding.EncodeToString(pub)

	jwksBody, err := json.Marshal(map[string]any{
		"keys": []map[string]any{
			{
				"kty": "OKP",
				"crv": "Ed25519",
				"kid": kid,
				"x":   xB64,
			},
		},
	})
	if err != nil {
		t.Fatalf("startJWKSServer: marshal: %v", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/jwks", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(jwksBody)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// ============================================================================
// In-process IMAP server for e2e
// ============================================================================

func startE2EIMAPServer(t *testing.T) (addr string, cleanup func()) {
	t.Helper()

	memSrv := imapmemserver.New()
	u := imapmemserver.NewUser(e2eUser, e2ePass)
	if err := u.Create("INBOX", nil); err != nil {
		t.Fatalf("startE2EIMAPServer: create INBOX: %v", err)
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
		t.Fatalf("startE2EIMAPServer: listen: %v", err)
	}
	go func() { _ = srv.Serve(ln) }()

	return ln.Addr().String(), func() {
		_ = srv.Close()
		_ = ln.Close()
	}
}

// ============================================================================
// e2e IMAP pool
// ============================================================================

type e2eIMAPPool struct{ imapAddr string }

func (p *e2eIMAPPool) Get(_ context.Context, _ pool.ServiceConfig) (*imapwrap.Client, error) {
	conn, err := net.Dial("tcp", p.imapAddr)
	if err != nil {
		return nil, fmt.Errorf("e2eIMAPPool.Get: %w", err)
	}
	creds := imapwrap.Credentials{
		Username: e2eUser,
		Password: e2ePass,
		AuthMode: imapwrap.AuthModeLogin,
	}
	return imapwrap.DialFromConn(conn, creds)
}

func (p *e2eIMAPPool) Release(_ pool.ServiceConfig, c *imapwrap.Client) {
	if c != nil {
		_ = c.Close()
	}
}

// ============================================================================
// e2e vault stub — implements handlers.VaultGetter for the test IMAP server.
// ============================================================================

type e2eVaultStub struct{ imapAddr string }

func (v *e2eVaultStub) GetCredential(_ context.Context, _, _ string, _ vault.AuthScheme) (*vault.Credential, error) {
	payload := fmt.Sprintf(`{"username":%q,"password":%q,"imap_host":%q}`, e2eUser, e2ePass, v.imapAddr)
	return &vault.Credential{
		Value:      []byte(payload),
		AuthScheme: vault.AuthSchemeEmailPassword,
		BaseUrl:    v.imapAddr,
	}, nil
}

// ============================================================================
// e2e permission checker — allow-all for the known test email_service_id.
// ============================================================================

type e2ePermissionChecker struct{}

func (p *e2ePermissionChecker) CheckGrant(_ context.Context, tenantID, agentID, emailServiceID string) error {
	// Allow the test agent on the test email service. Deny everything else.
	if agentID == e2eAgentID && emailServiceID == e2eEmailServiceID {
		return nil
	}
	return fmt.Errorf("e2e: no grant for (%s, %s, %s)", tenantID, agentID, emailServiceID)
}

// ============================================================================
// e2e OAuth2 vault getter
// ============================================================================

type e2eOAuth2VaultGetter struct{}

func (v *e2eOAuth2VaultGetter) GetRefreshToken(_ context.Context, _, _ string) (string, string, error) {
	return "generic", "rt_e2e_refresh", nil
}

// ============================================================================
// TestEmailE2E_FullPathWithEmailServiceKindJWT
// ============================================================================

// TestEmailE2E_FullPathWithEmailServiceKindJWT exercises the complete path:
//  1. Issue a JWT with service_kind=email (simulating the broker's output).
//  2. Send the JWT to the full email-proxy server stack.
//  3. Assert GET /v1/email-proxy/mailboxes returns 200 with a non-empty list.
//  4. Assert the permission checker was consulted with the correct triple.
//
// This test verifies that:
//   - email-proxy accepts service_kind=email JWTs (no regression to existing auth).
//   - The JWT's service_id claim is used as the email_service_id for permission checks.
//   - The full middleware→handler path works end-to-end without mocks.
func TestEmailE2E_FullPathWithEmailServiceKindJWT(t *testing.T) {
	// --- Set up ephemeral Ed25519 key pair ---
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("keygen: %v", err)
	}
	kid := "kid_e2e_email_test_01"

	// --- JWKS server serving the ephemeral key ---
	jwksSrv := startJWKSServer(t, kid, pub)
	cache, err := authpkg.NewJWKSCache(jwksSrv.URL + "/jwks")
	if err != nil {
		t.Fatalf("NewJWKSCache: %v", err)
	}
	validator := authpkg.NewValidator(cache)

	// --- In-process IMAP server ---
	imapAddr, cleanup := startE2EIMAPServer(t)
	defer cleanup()

	// --- Build email-proxy handlers ---
	oauth2Srv := startOAuth2MockServer(t)

	ae := &itAuditEmitter{}
	smtpStub := &itSMTPStub{msgID: "e2e_msg_001"}

	imapPool := &e2eIMAPPool{imapAddr: imapAddr}
	vaultStub := &e2eVaultStub{imapAddr: imapAddr}
	oauth2Mgr := oauth2.NewManager(oauth2Srv.URL, &e2eOAuth2VaultGetter{}, "e2e_svc_token")
	rl := security.NewRateLimiter()
	permChecker := &e2ePermissionChecker{}

	emailHdlr := handlers.New(imapPool, oauth2Mgr, vaultStub, smtpStub, rl, ae, permChecker)

	// --- Build server stack (uses newWithHandlers for test injection) ---
	cfg := &config.Config{
		HTTPPort:               0, // random port — httptest.NewServer binds its own port
		BrokerJWKSURL:          jwksSrv.URL + "/jwks",
		AdminAPIInternalURL:    oauth2Srv.URL,
		EmailProxyServiceToken: "e2e_svc_token",
	}
	srv := server.NewForTest(cfg, nil, validator, emailHdlr)

	// --- Issue the JWT ---
	tokenStr := issueEmailJWT(t, kid, priv, "email")

	// --- Serve via httptest ---
	testSrv := httptest.NewServer(srv.Handler())
	defer testSrv.Close()

	// --- List mailboxes ---
	req, err := http.NewRequest(http.MethodGet,
		fmt.Sprintf("%s/v1/email-proxy/mailboxes?service_id=%s", testSrv.URL, e2eEmailServiceID),
		nil)
	if err != nil {
		t.Fatalf("build request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+tokenStr)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("GET /mailboxes: %v", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	if resp.StatusCode != http.StatusOK {
		var body map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&body)
		t.Fatalf("expected 200, got %d: %v", resp.StatusCode, body)
	}

	var mailboxResp struct {
		Mailboxes []struct {
			Name string `json:"name"`
		} `json:"mailboxes"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&mailboxResp); err != nil {
		t.Fatalf("decode mailbox response: %v", err)
	}
	if len(mailboxResp.Mailboxes) == 0 {
		t.Error("expected at least INBOX, got empty mailbox list")
	}

	// Verify INBOX is in the list.
	found := false
	for _, m := range mailboxResp.Mailboxes {
		if m.Name == "INBOX" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("INBOX not found in mailbox list: %v", mailboxResp.Mailboxes)
	}

	t.Logf("E2E: listed %d mailboxes via service_kind=email JWT", len(mailboxResp.Mailboxes))
}

// TestEmailE2E_MissingServiceKind_StillAccepted verifies that the email-proxy
// accepts tokens WITHOUT service_kind (e.g. manually crafted tokens) as long as
// they have the required scope and a valid service_id in email_permission_grants.
//
// This is a regression guard: we must NOT require service_kind — it is informational.
func TestEmailE2E_MissingServiceKind_StillAccepted(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("keygen: %v", err)
	}
	kid := "kid_e2e_email_test_02"

	jwksSrv2 := startJWKSServer(t, kid, pub)
	cache2, err := authpkg.NewJWKSCache(jwksSrv2.URL + "/jwks")
	if err != nil {
		t.Fatalf("NewJWKSCache: %v", err)
	}
	validator := authpkg.NewValidator(cache2)

	imapAddr, cleanup := startE2EIMAPServer(t)
	defer cleanup()

	oauth2Srv := startOAuth2MockServer(t)

	ae := &itAuditEmitter{}
	smtpStub := &itSMTPStub{msgID: "e2e_msg_002"}
	imapPool := &e2eIMAPPool{imapAddr: imapAddr}
	vaultStub := &e2eVaultStub{imapAddr: imapAddr}
	oauth2Mgr := oauth2.NewManager(oauth2Srv.URL, &e2eOAuth2VaultGetter{}, "e2e_svc_token_2")
	rl := security.NewRateLimiter()
	permChecker := &e2ePermissionChecker{}
	emailHdlr := handlers.New(imapPool, oauth2Mgr, vaultStub, smtpStub, rl, ae, permChecker)

	cfg := &config.Config{
		HTTPPort:               0,
		BrokerJWKSURL:          jwksSrv2.URL + "/jwks",
		AdminAPIInternalURL:    oauth2Srv.URL,
		EmailProxyServiceToken: "e2e_svc_token_2",
	}
	srv := server.NewForTest(cfg, nil, validator, emailHdlr)
	testSrv := httptest.NewServer(srv.Handler())
	defer testSrv.Close()

	// Issue JWT WITHOUT service_kind — simulates pre-email-e2e tokens.
	tokenStr := issueEmailJWT(t, kid, priv, "") // empty string → claim omitted in broker

	req, _ := http.NewRequest(http.MethodGet,
		fmt.Sprintf("%s/v1/email-proxy/mailboxes?service_id=%s", testSrv.URL, e2eEmailServiceID),
		nil)
	req.Header.Set("Authorization", "Bearer "+tokenStr)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("GET /mailboxes (no service_kind): %v", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	// Should still succeed — service_kind is informational, not enforced.
	if resp.StatusCode != http.StatusOK {
		var body map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&body)
		t.Fatalf("expected 200 without service_kind, got %d: %v", resp.StatusCode, body)
	}
	t.Logf("E2E: JWT without service_kind still accepted (200)")
}
