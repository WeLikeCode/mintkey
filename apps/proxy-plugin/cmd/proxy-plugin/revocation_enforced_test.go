package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/changes"
)

// changesSubscriberSource is the handler's ability to build the change
// subscriber over its own revocation sets. The test reaches it through an
// interface so that the test file names no symbol this change adds.
type changesSubscriberSource interface {
	changesSubscriber(dsn string, opts ...changes.SubscriberOption) *changes.Subscriber
}

// TestRevokedJTIIsRefusedBeforeVault_C_a33ad25b pins that a token revoked
// through the change channel is refused with 401 before the credential fetch,
// while a token of the same agent with another jti still reaches the vault.
func TestRevokedJTIIsRefusedBeforeVault_C_a33ad25b(t *testing.T) {
	h := testHandler()

	src, ok := any(h).(changesSubscriberSource)
	if !ok {
		t.Fatal("proxyHandler cannot build a change subscriber over its own sets")
	}
	sub := src.changesSubscriber("")
	if err := sub.HandleNotification(`{"event_type":"token.revoked","jti":"jti_01REVOKED"}`); err != nil {
		t.Fatalf("HandleNotification(token.revoked): %v", err)
	}

	revokedToken, revokedPub := buildTestJWTWithClaims(t, testSvcUUIDA, "agent_test", "jti_01REVOKED")
	h.pubKeys["testkey"] = revokedPub
	revokedReq := httptest.NewRequest(http.MethodGet, "/", nil)
	revokedReq.Header.Set("Authorization", "Bearer "+revokedToken)
	revokedRec := httptest.NewRecorder()
	h.ServeHTTP(revokedRec, revokedReq)

	if revokedRec.Code != http.StatusUnauthorized {
		t.Fatalf("revoked token: status = %d, want %d", revokedRec.Code, http.StatusUnauthorized)
	}
	if body := revokedRec.Body.String(); !strings.Contains(body, "token revoked") {
		t.Fatalf("revoked token: body = %q, want it to contain %q", body, "token revoked")
	}

	otherToken, otherPub := buildTestJWTWithClaims(t, testSvcUUIDA, "agent_test", "jti_01OTHER")
	h.pubKeys["testkey"] = otherPub
	otherReq := httptest.NewRequest(http.MethodGet, "/", nil)
	otherReq.Header.Set("Authorization", "Bearer "+otherToken)
	otherRec := httptest.NewRecorder()
	h.ServeHTTP(otherRec, otherReq)

	if otherRec.Code != http.StatusBadGateway {
		t.Fatalf("unrevoked jti: status = %d, want %d from the unreachable test vault", otherRec.Code, http.StatusBadGateway)
	}
}

// TestRevokedAgentIsRefusedAcrossIDForms_C_958f74fb pins that an agent revoked
// by its wire id is refused when the token carries its UUID, while a token of
// another agent still reaches the vault.
func TestRevokedAgentIsRefusedAcrossIDForms_C_958f74fb(t *testing.T) {
	h := testHandler()

	src, ok := any(h).(changesSubscriberSource)
	if !ok {
		t.Fatal("proxyHandler cannot build a change subscriber over its own sets")
	}
	sub := src.changesSubscriber("")
	if err := sub.HandleNotification(`{"event":"agent.revoked","agent_id":"agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"}`); err != nil {
		t.Fatalf("HandleNotification(agent.revoked): %v", err)
	}

	revokedToken, revokedPub := buildTestJWTWithClaims(t, testSvcUUIDA, "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd", "jti_01AAA")
	h.pubKeys["testkey"] = revokedPub
	revokedReq := httptest.NewRequest(http.MethodGet, "/", nil)
	revokedReq.Header.Set("Authorization", "Bearer "+revokedToken)
	revokedRec := httptest.NewRecorder()
	h.ServeHTTP(revokedRec, revokedReq)

	if revokedRec.Code != http.StatusUnauthorized {
		t.Fatalf("revoked agent: status = %d, want %d", revokedRec.Code, http.StatusUnauthorized)
	}
	if body := revokedRec.Body.String(); !strings.Contains(body, "token revoked") {
		t.Fatalf("revoked agent: body = %q, want it to contain %q", body, "token revoked")
	}

	otherToken, otherPub := buildTestJWTWithClaims(t, testSvcUUIDA, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "jti_01BBB")
	h.pubKeys["testkey"] = otherPub
	otherReq := httptest.NewRequest(http.MethodGet, "/", nil)
	otherReq.Header.Set("Authorization", "Bearer "+otherToken)
	otherRec := httptest.NewRecorder()
	h.ServeHTTP(otherRec, otherReq)

	if otherRec.Code != http.StatusBadGateway {
		t.Fatalf("unrevoked agent: status = %d, want %d from the unreachable test vault", otherRec.Code, http.StatusBadGateway)
	}
}
