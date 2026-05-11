package revocation_test

import (
	"testing"
	"time"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/revocation"
)

func TestJTISetAddContains(t *testing.T) {
	s := revocation.NewJTIRevocationSet(100)

	if s.Contains("jti_01DEF") {
		t.Fatal("expected jti_01DEF not to be in set before Add")
	}
	if s.Len() != 0 {
		t.Fatalf("expected Len=0, got %d", s.Len())
	}

	s.Add("jti_01DEF")

	if !s.Contains("jti_01DEF") {
		t.Fatal("expected jti_01DEF to be in set after Add")
	}
	if s.Len() != 1 {
		t.Fatalf("expected Len=1, got %d", s.Len())
	}

	if s.Contains("jti_OTHER") {
		t.Fatal("jti_OTHER should not be in set")
	}
}

func TestJTISetEviction(t *testing.T) {
	s := revocation.NewJTIRevocationSet(100)

	// Add entries with a very short TTL by manipulating the revoked_at via the
	// public API. We use a negative Evict TTL trick: add entries, then evict with
	// a TTL of 0 (everything added "in the past" relative to Now-0 = Now).
	//
	// The implementation stores revoked_at = time.Now() at Add time. Evict
	// removes entries older than ttl. Using ttl=0 removes entries whose
	// revoked_at is strictly before time.Now(), which should be all of them
	// immediately (within a goroutine scheduler cycle).
	//
	// To make the test reliable we wait 1ms before evicting, ensuring the
	// timestamps are solidly in the past relative to now-0.

	s.Add("jti_stale_1")
	s.Add("jti_stale_2")
	s.Add("jti_stale_3")

	if s.Len() != 3 {
		t.Fatalf("expected Len=3 before eviction, got %d", s.Len())
	}

	time.Sleep(2 * time.Millisecond) // ensure revoked_at < now

	// Evict anything older than 0 — i.e., anything added before right now.
	s.Evict(0)

	if s.Len() != 0 {
		t.Fatalf("expected Len=0 after eviction, got %d", s.Len())
	}
	if s.Contains("jti_stale_1") || s.Contains("jti_stale_2") || s.Contains("jti_stale_3") {
		t.Fatal("stale entries should have been evicted")
	}
}

func TestJTISetMaxSizeCap(t *testing.T) {
	const max = 3
	s := revocation.NewJTIRevocationSet(max)

	for i := range max + 5 {
		s.Add(string(rune('A' + i)))
	}

	// Should be capped at max, not beyond.
	if s.Len() > max {
		t.Fatalf("expected Len<=%d, got %d", max, s.Len())
	}
}
