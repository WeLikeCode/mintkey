package changes_test

import (
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/changes"
	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

// TestHandleNotificationAcceptsEventKey_C_c9a9a91e pins that HandleNotification
// reads the event name from "event_type", or from "event" when "event_type" is
// absent, and that "event_type" wins when both are present.
func TestHandleNotificationAcceptsEventKey_C_c9a9a91e(t *testing.T) {
	agents := revocation.NewAgentRevocationSet()
	jtis := revocation.NewJTIRevocationSet(100_000)
	sub := changes.NewSubscriber("", agents, jtis, nil)

	payloads := []string{
		`{"event":"agent.revoked","agent_id":"agent_01ABC"}`,
		`{"event":"token.revoked","jti":"jti_01DEF"}`,
		`{"event_type":"token.revoked","event":"agent.revoked","jti":"jti_01XYZ","agent_id":"agent_01XYZ"}`,
	}
	for _, payload := range payloads {
		if err := sub.HandleNotification(payload); err != nil {
			t.Fatalf("HandleNotification(%s): %v", payload, err)
		}
	}

	if !agents.Contains("agent_01ABC") {
		t.Error("agent set does not contain agent_01ABC from the payload keyed by event")
	}
	if !jtis.Contains("jti_01DEF") {
		t.Error("token set does not contain jti_01DEF from the payload keyed by event")
	}
	if !jtis.Contains("jti_01XYZ") {
		t.Error("token set does not contain jti_01XYZ from the payload whose event_type wins")
	}
	if agents.Contains("agent_01XYZ") {
		t.Error("agent set contains agent_01XYZ, but event_type token.revoked should win over event agent.revoked")
	}
}
