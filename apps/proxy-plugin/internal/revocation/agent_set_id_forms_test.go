package revocation_test

import (
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

// TestAgentSetMatchesWireAndUUIDForms_C_f100318b pins that every wire and UUID
// form of one agent id denotes the same revoked agent.
func TestAgentSetMatchesWireAndUUIDForms_C_f100318b(t *testing.T) {
	s := revocation.NewAgentRevocationSet()
	s.Add("agent_3C7JAGMBGR9EMRS2AVGXDHQXDX")

	sameAgent := []string{
		"6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd",
		"6C3C950A-2E18-4BA9-8C89-5B875B1BF5BD",
		"agent_6c3c950a2e184ba98c895b875b1bf5bd",
		"agent_3c7jagmbgr9emrs2avgxdhqxdx",
	}
	for _, id := range sameAgent {
		if !s.Contains(id) {
			t.Errorf("Contains(%q) = false, want true for agent_3C7JAGMBGR9EMRS2AVGXDHQXDX", id)
		}
	}

	if s.Contains("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") {
		t.Error("Contains(aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa) = true, want false")
	}
}

// TestAgentSetAddedUUIDMatchesWireFormAndIgnoresEmpty_C_3d2301c4 pins that a
// UUID added to the set matches its wire form and that Add("") adds nothing.
func TestAgentSetAddedUUIDMatchesWireFormAndIgnoresEmpty_C_3d2301c4(t *testing.T) {
	s := revocation.NewAgentRevocationSet()
	s.Add("6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd")
	s.Add("")

	if !s.Contains("agent_3C7JAGMBGR9EMRS2AVGXDHQXDX") {
		t.Error("Contains(agent_3C7JAGMBGR9EMRS2AVGXDHQXDX) = false, want true after adding its UUID")
	}
	if got := s.Len(); got != 1 {
		t.Fatalf("Len() = %d, want 1 (the UUID; Add(\"\") adds nothing)", got)
	}
}
