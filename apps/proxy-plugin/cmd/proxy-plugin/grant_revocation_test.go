package main

import (
	"encoding/json"
	"net/http"
	"reflect"
	"strings"
	"testing"
	"time"
	"unsafe"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/changes"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

// grantAgentWire, grantServiceWire and their UUID forms are the pair the
// revocation scenarios use: the wire forms decode to the UUID forms.
const (
	grantAgentWire   = "agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"
	grantServiceWire = "svc_5ANANANANANANANANANANANANA"
	grantAgentUUID   = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
	grantServiceUUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
	grantOtherSvc    = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
	grantOtherAgent  = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
)

// applyRevocation builds the agent.permission.revoked payload of the scenarios
// and hands it to the handler's own change subscriber. revokedAt nil omits the
// field; a time.Time is written the way admin-api's datetime.isoformat() does.
func applyRevocation(t *testing.T, h *proxyHandler, agentWire, serviceWire string, revokedAt any) error {
	t.Helper()
	payload := map[string]any{
		"event":         "agent.permission.revoked",
		"event_type":    "agent.permission.revoked",
		"tenant_id":     "11111111-2222-3333-4444-555555555555",
		"permission_id": "perm_01X",
		"agent_id":      agentWire,
		"service_id":    serviceWire,
	}
	switch v := revokedAt.(type) {
	case nil:
	case time.Time:
		payload["revoked_at"] = v.UTC().Format("2006-01-02T15:04:05.000000-07:00")
	default:
		payload["revoked_at"] = v
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal agent.permission.revoked payload: %v", err)
	}
	return h.changesSubscriber("").HandleNotification(string(raw))
}

// grantToken signs a token of (aud, sub) with the extra claims merged in and
// loads its key into the handler's JWKS cache. extra may override sub and add
// iat; a token with no iat claim is built without one.
func grantToken(t *testing.T, h *proxyHandler, aud, sub string, extra map[string]any) string {
	t.Helper()
	claims := map[string]any{"sub": sub}
	for k, v := range extra {
		claims[k] = v
	}
	token, pub := buildScopeClaimsJWT(t, aud, claims)
	h.pubKeys["testkey"] = pub
	return token
}

// assertGrantRevoked asserts that the request is refused with 401 and the
// revoked-token body, before any credential fetch.
func assertGrantRevoked(t *testing.T, h *proxyHandler, token, label string) {
	t.Helper()
	rw := scopeRequest(t, h, token, http.MethodGet, "/")
	if rw.Code != http.StatusUnauthorized {
		t.Fatalf("%s: status = %d, want %d (body: %s)", label, rw.Code, http.StatusUnauthorized, rw.Body.String())
	}
	if body := rw.Body.String(); !strings.Contains(body, "token revoked") {
		t.Fatalf("%s: body = %q, want it to contain %q", label, body, "token revoked")
	}
}

// TestRevokedGrantRefusesEarlierTokens covers the scenario "tokens issued
// before the revocation are refused, later ones and other pairs are not".
func TestRevokedGrantRefusesEarlierTokens_C_bbfa63fe(t *testing.T) {
	h := testHandler()
	revokedAt := time.Now().Add(-60 * time.Second)
	if err := applyRevocation(t, h, grantAgentWire, grantServiceWire, revokedAt); err != nil {
		t.Fatalf("apply agent.permission.revoked: %v", err)
	}
	r := revokedAt.Unix()

	assertGrantRevoked(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{"iat": r - 60}), "iat R-60")
	assertGrantRevoked(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{"iat": r - 1}), "iat R-1")
	assertGrantRevoked(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{"iat": r}), "iat R")

	assertScopeReachesVault(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{"iat": r + 1}), http.MethodGet, "/")
	assertScopeReachesVault(t, h, grantToken(t, h, grantOtherSvc, grantAgentUUID, map[string]any{"iat": r - 1}), http.MethodGet, "/")
	assertScopeReachesVault(t, h, grantToken(t, h, grantServiceUUID, grantOtherAgent, map[string]any{"iat": r - 1}), http.MethodGet, "/")

	var metrics strings.Builder
	if err := h.metrics.WriteMetricsTo(&metrics); err != nil {
		t.Fatalf("WriteMetricsTo: %v", err)
	}
	want := `mintkey_proxy_denied_total{service="` + grantServiceUUID + `",reason="revoked"} 3`
	if !strings.Contains(metrics.String(), want) {
		t.Fatalf("metrics do not hold %q:\n%s", want, metrics.String())
	}
}

// TestTokenWithoutUsableIatIsRefused covers the scenario "a token without a
// usable iat is refused while an entry exists".
func TestTokenWithoutUsableIatIsRefused_C_b304eac3(t *testing.T) {
	h := testHandler()
	if err := applyRevocation(t, h, grantAgentWire, grantServiceWire, time.Now().Add(-60*time.Second)); err != nil {
		t.Fatalf("apply agent.permission.revoked: %v", err)
	}

	assertGrantRevoked(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, nil), "no iat")
	assertGrantRevoked(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{"iat": "123"}), `iat "123"`)
	assertGrantRevoked(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{"iat": 0}), "iat 0")
	assertGrantRevoked(t, h, grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{"iat": -5}), "iat -5")

	// No event applied: a token without iat is not refused.
	fresh := testHandler()
	assertScopeReachesVault(t, fresh, grantToken(t, fresh, grantServiceUUID, grantAgentUUID, nil), http.MethodGet, "/")
}

// TestOldRevocationAddsNothingAndFutureCountsAsNow covers the scenario "an old
// revocation adds nothing and a future one counts as received now".
func TestOldRevocationAddsNothingAndFutureCountsAsNow_C_650441f7(t *testing.T) {
	oldRevocation := testHandler()
	if err := applyRevocation(t, oldRevocation, grantAgentWire, grantServiceWire, time.Now().Add(-3700*time.Second)); err != nil {
		t.Fatalf("apply old agent.permission.revoked: %v", err)
	}
	oldToken := grantToken(t, oldRevocation, grantServiceUUID, grantAgentUUID, map[string]any{
		"iat": time.Now().Add(-3800 * time.Second).Unix(),
	})
	assertScopeReachesVault(t, oldRevocation, oldToken, http.MethodGet, "/")

	futureRevocation := testHandler()
	if err := applyRevocation(t, futureRevocation, grantAgentWire, grantServiceWire, time.Now().Add(time.Hour)); err != nil {
		t.Fatalf("apply future agent.permission.revoked: %v", err)
	}
	afterReceipt := grantToken(t, futureRevocation, grantServiceUUID, grantAgentUUID, map[string]any{
		"iat": time.Now().Add(5 * time.Second).Unix(),
	})
	assertScopeReachesVault(t, futureRevocation, afterReceipt, http.MethodGet, "/")

	beforeReceipt := grantToken(t, futureRevocation, grantServiceUUID, grantAgentUUID, map[string]any{
		"iat": time.Now().Add(-30 * time.Second).Unix(),
	})
	assertGrantRevoked(t, futureRevocation, beforeReceipt, "future revocation counts as received now")
}

// TestRevocationWithoutRevokedAtCountsFromReceipt covers the scenario "an event
// without revoked_at counts from its receipt".
func TestRevocationWithoutRevokedAtCountsFromReceipt_C_21c34307(t *testing.T) {
	h := testHandler()
	if err := applyRevocation(t, h, grantAgentWire, grantServiceWire, nil); err != nil {
		t.Fatalf("apply agent.permission.revoked without revoked_at: %v", err)
	}

	beforeReceipt := grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{
		"iat": time.Now().Add(-30 * time.Second).Unix(),
	})
	assertGrantRevoked(t, h, beforeReceipt, "iat 30s ago")

	afterReceipt := grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{
		"iat": time.Now().Add(5 * time.Second).Unix(),
	})
	assertScopeReachesVault(t, h, afterReceipt, http.MethodGet, "/")
}

// grantSetMethod returns the named method of the handler's own grant set,
// reached by reflection so that this test names no symbol the change adds.
func grantSetMethod(t *testing.T, set reflect.Value, name string) reflect.Value {
	t.Helper()
	method := set.MethodByName(name)
	if !method.IsValid() {
		t.Fatalf("GrantRevocationSet has no %s method", name)
	}
	return method
}

// TestGrantSetKeepsLaterAndDropsExpired covers the scenario "the set keeps the
// later revocation, counts its entries and drops expired ones".
func TestGrantSetKeepsLaterAndDropsExpired_C_e8ef472b(t *testing.T) {
	h := testHandler()
	field := reflect.ValueOf(h).Elem().FieldByName("revokedGrants")
	if !field.IsValid() {
		t.Fatal("proxyHandler has no revokedGrants field")
	}
	if field.Kind() != reflect.Ptr || field.IsNil() {
		t.Fatalf("proxyHandler.revokedGrants = %v, want a non-nil *GrantRevocationSet", field)
	}
	set := reflect.NewAt(field.Type(), unsafe.Pointer(field.UnsafeAddr())).Elem()

	add := grantSetMethod(t, set, "Add")
	refuses := grantSetMethod(t, set, "Refuses")
	length := grantSetMethod(t, set, "Len")

	addAt := func(agentID, serviceID string, revokedAt time.Time) {
		t.Helper()
		add.Call([]reflect.Value{reflect.ValueOf(agentID), reflect.ValueOf(serviceID), reflect.ValueOf(revokedAt)})
	}
	refusesAt := func(agentID, serviceID string, iat int64) bool {
		t.Helper()
		out := refuses.Call([]reflect.Value{
			reflect.ValueOf(agentID), reflect.ValueOf(serviceID), reflect.ValueOf(iat), reflect.ValueOf(true),
		})
		if len(out) != 1 || out[0].Kind() != reflect.Bool {
			t.Fatalf("Refuses returned %v, want one bool", out)
		}
		return out[0].Bool()
	}
	lenSet := func() int {
		t.Helper()
		out := length.Call(nil)
		if len(out) != 1 || out[0].Kind() != reflect.Int {
			t.Fatalf("Len returned %v, want one int", out)
		}
		return int(out[0].Int())
	}

	now := time.Now()
	secondPairAgent := grantOtherAgent
	secondPairSvc := grantOtherSvc
	thirdPairAgent := grantAgentUUID
	thirdPairSvc := grantServiceUUID

	addAt(grantAgentWire, grantServiceWire, now.Add(-120*time.Second))
	addAt(grantAgentWire, grantServiceWire, now.Add(-300*time.Second)) // out of order: earlier, must not replace

	if got := lenSet(); got != 1 {
		t.Fatalf("Len after two Add calls for one pair = %d, want 1", got)
	}
	if !refusesAt(grantAgentWire, grantServiceWire, now.Add(-130*time.Second).Unix()) {
		t.Fatal("Refuses(pair, iat 130s ago) = false, want true")
	}
	if refusesAt(grantAgentWire, grantServiceWire, now.Add(-100*time.Second).Unix()) {
		t.Fatal("Refuses(pair, iat 100s ago) = true, want false")
	}

	addAt(secondPairAgent, secondPairSvc, now.Add(-3629*time.Second-200*time.Millisecond))
	if got := lenSet(); got != 2 {
		t.Fatalf("Len after adding the second pair = %d, want 2", got)
	}

	time.Sleep(1500 * time.Millisecond)
	addAt(thirdPairAgent, thirdPairSvc, time.Now())

	if got := lenSet(); got != 2 {
		t.Fatalf("Len after the second pair expired and a third was added = %d, want 2", got)
	}
	if refusesAt(secondPairAgent, secondPairSvc, now.Add(-4000*time.Second).Unix()) {
		t.Fatal("Refuses(second pair, iat 4000s ago) = true, want false after its entry expired")
	}
}

// TestUnusableEventsAreNotApplied covers the scenario "an event that names no
// agent or no service is not applied".
func TestUnusableEventsAreNotApplied_C_7ac13f75(t *testing.T) {
	h := testHandler()

	base := map[string]any{
		"event":         "agent.permission.revoked",
		"event_type":    "agent.permission.revoked",
		"tenant_id":     "11111111-2222-3333-4444-555555555555",
		"permission_id": "perm_01X",
		"revoked_at":    time.Now().Add(-60 * time.Second).UTC().Format("2006-01-02T15:04:05.000000-07:00"),
	}
	cases := []struct {
		label     string
		agentID   *string
		serviceID *string
		wantField string
	}{
		{"agent_id missing", nil, stringPtr(grantServiceWire), "agent_id"},
		{"service_id missing", stringPtr(grantAgentWire), nil, "service_id"},
		{"both empty", stringPtr(""), stringPtr(""), ""},
		{"both missing", nil, nil, ""},
	}
	for _, c := range cases {
		payload := map[string]any{}
		for k, v := range base {
			payload[k] = v
		}
		if c.agentID != nil {
			payload["agent_id"] = *c.agentID
		}
		if c.serviceID != nil {
			payload["service_id"] = *c.serviceID
		}
		raw, err := json.Marshal(payload)
		if err != nil {
			t.Fatalf("%s: marshal payload: %v", c.label, err)
		}
		err = h.changesSubscriber("").HandleNotification(string(raw))
		if err == nil {
			t.Fatalf("%s: HandleNotification returned nil, want an error", c.label)
		}
		if c.wantField != "" && !strings.Contains(err.Error(), c.wantField) {
			t.Fatalf("%s: error = %q, want it to name %q", c.label, err.Error(), c.wantField)
		}
	}

	// Nothing was applied: a token of the pair still reaches the credential fetch.
	token := grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{
		"iat": time.Now().Add(-120 * time.Second).Unix(),
	})
	assertScopeReachesVault(t, h, token, http.MethodGet, "/")
}

// stringPtr returns a pointer to s for the table above.
func stringPtr(s string) *string { return &s }

// TestSubscriberWithoutGrantSetIgnoresPermissionRevoked covers the scenario "a
// subscriber built without the set ignores the event". The same event through
// the handler's subscriber, which carries the set, does change the handler, so
// the bare subscriber ignored it for lack of the set.
func TestSubscriberWithoutGrantSetIgnoresPermissionRevoked_C_9d6cd6b8(t *testing.T) {
	agents := revocation.NewAgentRevocationSet()
	jtis := revocation.NewJTIRevocationSet(100_000)
	sub := changes.NewSubscriber("", agents, jtis, nil)

	revoked := `{"event_type":"agent.permission.revoked","agent_id":"` + grantAgentWire +
		`","service_id":"` + grantServiceWire + `","revoked_at":"2026-11-25T10:00:00+00:00"}`
	if err := sub.HandleNotification(revoked); err != nil {
		t.Fatalf("subscriber without the grant set: HandleNotification(agent.permission.revoked) = %v, want nil", err)
	}
	if err := sub.HandleNotification(`{"event_type":"token.revoked","jti":"jti_01DEF"}`); err != nil {
		t.Fatalf("HandleNotification(token.revoked) = %v, want nil", err)
	}
	if !jtis.Contains("jti_01DEF") {
		t.Fatal("token revocation set does not contain jti_01DEF after token.revoked")
	}

	h := testHandler()
	revokedAt := time.Now().Add(-60 * time.Second)
	if err := applyRevocation(t, h, grantAgentWire, grantServiceWire, revokedAt); err != nil {
		t.Fatalf("apply agent.permission.revoked through the handler's subscriber: %v", err)
	}
	token := grantToken(t, h, grantServiceUUID, grantAgentUUID, map[string]any{
		"iat": revokedAt.Add(-60 * time.Second).Unix(),
	})
	assertGrantRevoked(t, h, token, "handler subscriber with the grant set")
}
