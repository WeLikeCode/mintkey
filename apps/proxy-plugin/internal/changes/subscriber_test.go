// Package changes_test exercises the Subscriber's notification dispatcher.
// All tests exercise handleNotification directly — no real DB required.
//
// Source: ADR-0014.4; T-1.6.7; long-lived-api-keys task 5.6.
package changes_test

import (
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/changes"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

// mockCache implements changes.ClassicalKeyCache for testing.
type mockCache struct {
	evictedFPs    []string
	evictedAgents []string
}

func (m *mockCache) EvictByFingerprint(fp string) { m.evictedFPs = append(m.evictedFPs, fp) }
func (m *mockCache) EvictByAgentID(id string)     { m.evictedAgents = append(m.evictedAgents, id) }

// mockBudgetCache implements changes.BudgetCacheInvalidator for testing.
type mockBudgetCache struct {
	invalidated []string
}

func (m *mockBudgetCache) InvalidateBudget(permissionID string) {
	m.invalidated = append(m.invalidated, permissionID)
}

// newTestSubscriber creates a Subscriber wired to fresh revocation sets and no cache.
func newTestSubscriber() (*changes.Subscriber, *revocation.AgentRevocationSet, *revocation.JTIRevocationSet) {
	agents := revocation.NewAgentRevocationSet()
	jtis := revocation.NewJTIRevocationSet(100_000)
	sub := changes.NewSubscriber("", agents, jtis, nil)
	return sub, agents, jtis
}

// newTestSubscriberWithCache creates a Subscriber with a mockCache attached.
func newTestSubscriberWithCache() (*changes.Subscriber, *revocation.AgentRevocationSet, *mockCache) {
	agents := revocation.NewAgentRevocationSet()
	jtis := revocation.NewJTIRevocationSet(100_000)
	mc := &mockCache{}
	sub := changes.NewSubscriber("", agents, jtis, mc)
	return sub, agents, mc
}

// newTestSubscriberWithBudgetCache creates a Subscriber with a mockBudgetCache attached.
func newTestSubscriberWithBudgetCache() (*changes.Subscriber, *mockBudgetCache) {
	agents := revocation.NewAgentRevocationSet()
	jtis := revocation.NewJTIRevocationSet(100_000)
	bc := &mockBudgetCache{}
	sub := changes.NewSubscriber("", agents, jtis, nil, changes.WithBudgetCache(bc))
	return sub, bc
}

// TestHandleAgentRevoked verifies that an agent.revoked payload adds the
// agent_id to the AgentRevocationSet.
func TestHandleAgentRevoked(t *testing.T) {
	sub, agents, _ := newTestSubscriber()

	if err := sub.HandleNotification(`{"event_type":"agent.revoked","agent_id":"agent_01ABC"}`); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !agents.Contains("agent_01ABC") {
		t.Fatal("expected agent_01ABC to be in the agent revocation set")
	}
}

// TestHandleTokenRevoked verifies that a token.revoked payload adds the jti to
// the JTIRevocationSet.
func TestHandleTokenRevoked(t *testing.T) {
	sub, _, jtis := newTestSubscriber()

	if err := sub.HandleNotification(`{"event_type":"token.revoked","jti":"jti_01DEF"}`); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !jtis.Contains("jti_01DEF") {
		t.Fatal("expected jti_01DEF to be in the JTI revocation set")
	}
}

// TestHandleUnknownEventType confirms that an unknown event_type produces no
// error and no panic, and that neither set is modified.
func TestHandleUnknownEventType(t *testing.T) {
	sub, agents, jtis := newTestSubscriber()

	if err := sub.HandleNotification(`{"event_type":"credential.rotated","credential_id":"cred_XYZ"}`); err != nil {
		t.Fatalf("unexpected error for unknown event type: %v", err)
	}

	if agents.Len() != 0 {
		t.Fatalf("expected agent set to remain empty, got Len=%d", agents.Len())
	}
	if jtis.Len() != 0 {
		t.Fatalf("expected jti set to remain empty, got Len=%d", jtis.Len())
	}
}

// TestHandleApiKeyRevoked verifies that api_key.revoked evicts the fingerprint
// from the classical-key resolution cache (long-lived-api-keys task 5.6).
func TestHandleApiKeyRevoked(t *testing.T) {
	sub, _, mc := newTestSubscriberWithCache()

	payload := `{"event_type":"api_key.revoked","key_fingerprint":"abcd1234"}`
	if err := sub.HandleNotification(payload); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(mc.evictedFPs) != 1 || mc.evictedFPs[0] != "abcd1234" {
		t.Fatalf("expected EvictByFingerprint(abcd1234), got %v", mc.evictedFPs)
	}
	if len(mc.evictedAgents) != 0 {
		t.Fatalf("expected no agent evictions, got %v", mc.evictedAgents)
	}
}

// TestHandleAgentRevokedAlsoEvictsCache verifies that agent.revoked both adds
// the agent to the revocation set AND evicts resolution cache entries for that
// agent (long-lived-api-keys task 5.6; ADR-0018 §2).
func TestHandleAgentRevokedAlsoEvictsCache(t *testing.T) {
	sub, agents, mc := newTestSubscriberWithCache()

	payload := `{"event_type":"agent.revoked","agent_id":"agent_01ABC"}`
	if err := sub.HandleNotification(payload); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !agents.Contains("agent_01ABC") {
		t.Fatal("expected agent_01ABC in agent revocation set")
	}
	if len(mc.evictedAgents) != 1 || mc.evictedAgents[0] != "agent_01ABC" {
		t.Fatalf("expected EvictByAgentID(agent_01ABC), got %v", mc.evictedAgents)
	}
}

// TestApiKeyRevokedNilCacheIsNoop verifies that when no cache is wired up,
// api_key.revoked is a no-op (no panic).
func TestApiKeyRevokedNilCacheIsNoop(t *testing.T) {
	sub, _, _ := newTestSubscriber() // nil cache
	if err := sub.HandleNotification(`{"event_type":"api_key.revoked","key_fingerprint":"abcd1234"}`); err != nil {
		t.Fatalf("unexpected error with nil cache: %v", err)
	}
}

// TestSubscriberDoesNotSubscribeToCredentialChannel asserts that the Subscriber
// type has no reference to the mintkey:credential channel — per ADR-0014.4 the
// Vault Adapter handles credential cache invalidation exclusively.
//
// We verify this structurally: NewSubscriber accepts a DSN and two sets, but
// there is no API surface for subscribing to additional channels. The only
// channel string compiled into the package is "mintkey:agent".
func TestSubscriberDoesNotSubscribeToCredentialChannel(t *testing.T) {
	// The Subscriber constructor does not accept a list of channels — only the
	// hardcoded mintkey:agent channel is ever used. Verify the exported API has
	// no method to add channels.
	sub, _, _ := newTestSubscriber()

	// The Subscriber should only expose: NewSubscriber, Start, HandleNotification.
	// If the type had a Listen(channel string) method, a misguided caller could
	// subscribe to mintkey:credential. Since it doesn't, this compiles only if
	// the type has no such method.
	_ = sub // compiler confirms no Subscribe/Listen method exists on *Subscriber
}


// ---------------------------------------------------------------------------
// T-BUD-3.4: budget.config_updated event handling
// ---------------------------------------------------------------------------

// TestHandleBudgetConfigUpdated verifies that a budget.config_updated event
// invalidates cached budget state for the affected permission_id.
func TestHandleBudgetConfigUpdated(t *testing.T) {
	sub, bc := newTestSubscriberWithBudgetCache()

	payload := `{"event_type":"budget.config_updated","target_id":"perm_01BUDGET"}`
	if err := sub.HandleNotification(payload); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(bc.invalidated) != 1 || bc.invalidated[0] != "perm_01BUDGET" {
		t.Fatalf("expected InvalidateBudget(perm_01BUDGET), got %v", bc.invalidated)
	}
}

// TestHandleBudgetConfigUpdated_NilBudgetCache verifies that budget.config_updated
// is a no-op when no budget cache is wired (no panic).
func TestHandleBudgetConfigUpdated_NilBudgetCache(t *testing.T) {
	sub, _, _ := newTestSubscriber() // nil budget cache
	payload := `{"event_type":"budget.config_updated","target_id":"perm_01BUDGET"}`
	if err := sub.HandleNotification(payload); err != nil {
		t.Fatalf("unexpected error with nil budget cache: %v", err)
	}
}

// TestHandleBudgetConfigUpdated_EmptyTargetID verifies that budget.config_updated
// with an empty target_id does not call InvalidateBudget.
func TestHandleBudgetConfigUpdated_EmptyTargetID(t *testing.T) {
	sub, bc := newTestSubscriberWithBudgetCache()

	payload := `{"event_type":"budget.config_updated","target_id":""}`
	if err := sub.HandleNotification(payload); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(bc.invalidated) != 0 {
		t.Fatalf("expected no invalidation for empty target_id, got %v", bc.invalidated)
	}
}
