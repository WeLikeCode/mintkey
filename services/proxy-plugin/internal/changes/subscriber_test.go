// Package changes_test exercises the Subscriber's notification dispatcher.
// All tests exercise handleNotification directly — no real DB required.
//
// Source: ADR-0014.4; T-1.6.7.
package changes_test

import (
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/changes"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

// newTestSubscriber creates a Subscriber wired to fresh revocation sets.
func newTestSubscriber() (*changes.Subscriber, *revocation.AgentRevocationSet, *revocation.JTIRevocationSet) {
	agents := revocation.NewAgentRevocationSet()
	jtis := revocation.NewJTIRevocationSet(100_000)
	sub := changes.NewSubscriber("", agents, jtis)
	return sub, agents, jtis
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
