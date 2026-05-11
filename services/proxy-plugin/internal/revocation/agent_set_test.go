package revocation_test

import (
	"fmt"
	"sync"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

func TestAgentSetAddContains(t *testing.T) {
	s := revocation.NewAgentRevocationSet()

	if s.Contains("agent_01ABC") {
		t.Fatal("expected agent_01ABC not to be in set before Add")
	}
	if s.Len() != 0 {
		t.Fatalf("expected Len=0, got %d", s.Len())
	}

	s.Add("agent_01ABC")

	if !s.Contains("agent_01ABC") {
		t.Fatal("expected agent_01ABC to be in set after Add")
	}
	if s.Len() != 1 {
		t.Fatalf("expected Len=1, got %d", s.Len())
	}

	// A different ID must not be present.
	if s.Contains("agent_OTHER") {
		t.Fatal("agent_OTHER should not be in set")
	}
}

func TestAgentSetConcurrentAdd(t *testing.T) {
	s := revocation.NewAgentRevocationSet()
	const goroutines = 50

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := range goroutines {
		i := i
		go func() {
			defer wg.Done()
			s.Add(fmt.Sprintf("agent_%02d", i))
		}()
	}
	wg.Wait()

	if s.Len() != goroutines {
		t.Fatalf("expected Len=%d after concurrent adds, got %d", goroutines, s.Len())
	}
	for i := range goroutines {
		id := fmt.Sprintf("agent_%02d", i)
		if !s.Contains(id) {
			t.Errorf("expected %q to be in set", id)
		}
	}
}
