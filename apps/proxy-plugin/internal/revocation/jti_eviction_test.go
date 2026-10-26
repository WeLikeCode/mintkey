package revocation_test

import (
	"context"
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

// evictionRunner is the eviction loop under test. The test reaches it through
// an interface so that the test file names no symbol this change adds.
type evictionRunner interface {
	RunEviction(ctx context.Context, interval, retention time.Duration)
}

// TestJTIRunEvictionDropsEntriesPastRetention_C_bb2b48de pins that the
// eviction loop drops ids older than the retention, keeps ids younger than it,
// and returns once its context is cancelled.
func TestJTIRunEvictionDropsEntriesPastRetention_C_bb2b48de(t *testing.T) {
	old := revocation.NewJTIRevocationSet(10)
	old.Add("jti_old")
	fresh := revocation.NewJTIRevocationSet(10)
	fresh.Add("jti_new")

	oldRunner, ok := any(old).(evictionRunner)
	if !ok {
		t.Fatal("JTIRevocationSet has no RunEviction(ctx, interval, retention) method")
	}
	freshRunner, ok := any(fresh).(evictionRunner)
	if !ok {
		t.Fatal("JTIRevocationSet has no RunEviction(ctx, interval, retention) method")
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	oldDone := make(chan struct{})
	freshDone := make(chan struct{})
	go func() {
		oldRunner.RunEviction(ctx, 10*time.Millisecond, time.Nanosecond)
		close(oldDone)
	}()
	go func() {
		freshRunner.RunEviction(ctx, 10*time.Millisecond, time.Hour)
		close(freshDone)
	}()

	deadline := time.Now().Add(2 * time.Second)
	for old.Len() != 0 {
		if time.Now().After(deadline) {
			t.Fatalf("after 2s the set with a 1ns retention still holds %d entries, want 0", old.Len())
		}
		time.Sleep(10 * time.Millisecond)
	}

	if !fresh.Contains("jti_new") {
		t.Fatal("the set with a one-hour retention lost jti_new, want it kept")
	}

	cancel()

	dones := map[string]<-chan struct{}{
		"1ns retention":      oldDone,
		"one-hour retention": freshDone,
	}
	for name, done := range dones {
		select {
		case <-done:
		case <-time.After(2 * time.Second):
			t.Fatalf("%s RunEviction did not return within 2s after the context was cancelled", name)
		}
	}
}
