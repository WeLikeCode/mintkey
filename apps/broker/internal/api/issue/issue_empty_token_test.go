package issue_test

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/mintkey/mintkey/packages/go/auditq"
	"github.com/mintkey/mintkey/services/broker/internal/api/issue"
	"github.com/mintkey/mintkey/services/broker/internal/issuer"
	"github.com/mintkey/mintkey/services/broker/internal/keys"
)

type countingAudit struct {
	events int
}

func (a *countingAudit) Enqueue(auditq.Event) {
	a.events++
}

func newEmptyTokenIssuer(t *testing.T) *issuer.Issuer {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ring := keys.NewKeyRing()
	ring.Add("kid_01TESTISSUEID0000000000000", pub)
	return issuer.New(priv, "kid_01TESTISSUEID0000000000000", ring)
}

func validEmptyTokenIssueBody(t *testing.T) []byte {
	t.Helper()
	b, err := json.Marshal(map[string]any{
		"agent_id":    "agent_01HZ0000000000000000000001",
		"service_id":  "svc_01HZ0000000000000000000002",
		"tenant_id":   "tenant_01HZ0000000000000000000003",
		"scope":       "read",
		"ttl_seconds": 300,
	})
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func emptyTokenIssueRequest(t *testing.T, header *string) *http.Request {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/issue", bytes.NewReader(validEmptyTokenIssueBody(t)))
	req.Header.Set("Content-Type", "application/json")
	if header != nil {
		req.Header.Set("X-Mintkey-Service-Token", *header)
	}
	return req
}

func assertIssueUnauthenticated(t *testing.T, w *httptest.ResponseRecorder) {
	t.Helper()
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401; body: %s", w.Code, w.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if body["mintkey:code"] != "unauthenticated" {
		t.Fatalf("mintkey:code = %v, want unauthenticated", body["mintkey:code"])
	}
	if _, ok := body["token"]; ok {
		t.Fatalf("response holds a token field: %v", body)
	}
}

func TestIssue_EmptyConfiguredToken_NoHeader_Returns401_C_912521e8(t *testing.T) {
	audit := &countingAudit{}
	h := issue.NewHandlerWithAudit(newEmptyTokenIssuer(t), "", audit)

	w := httptest.NewRecorder()
	h.ServeHTTP(w, emptyTokenIssueRequest(t, nil))

	assertIssueUnauthenticated(t, w)
	if audit.events != 0 {
		t.Fatalf("audit received %d event(s), want 0", audit.events)
	}
}

func TestIssue_EmptyConfiguredToken_EmptyHeader_Returns401_C_8cc6b8bf(t *testing.T) {
	audit := &countingAudit{}
	h := issue.NewHandlerWithAudit(newEmptyTokenIssuer(t), "", audit)

	empty := ""
	w := httptest.NewRecorder()
	h.ServeHTTP(w, emptyTokenIssueRequest(t, &empty))

	assertIssueUnauthenticated(t, w)
	if audit.events != 0 {
		t.Fatalf("audit received %d event(s), want 0", audit.events)
	}
}

func TestIssue_EmptyConfiguredToken_AnyHeader_Returns401_C_71da8c1f_C_912521e8(t *testing.T) {
	audit := &countingAudit{}
	h := issue.NewHandlerWithAudit(newEmptyTokenIssuer(t), "", audit)

	anyHeader := "some-token"
	w := httptest.NewRecorder()
	h.ServeHTTP(w, emptyTokenIssueRequest(t, &anyHeader))

	assertIssueUnauthenticated(t, w)
	if audit.events != 0 {
		t.Fatalf("audit received %d event(s), want 0", audit.events)
	}

	// The same empty configuration must also refuse a request that carries no header at all.
	w = httptest.NewRecorder()
	h.ServeHTTP(w, emptyTokenIssueRequest(t, nil))

	assertIssueUnauthenticated(t, w)
	if audit.events != 0 {
		t.Fatalf("audit received %d event(s) after both requests, want 0", audit.events)
	}
}
