package ulid_test

import (
	"strings"
	"testing"

	"github.com/mintkey/mintkey/packages/go/ulid"
)

var validPrefixes = []string{
	"tenant_", "operator_", "agent_", "svc_", "cred_",
	"perm_", "audit_", "change_", "session_", "system_",
	"jti_", "kid_",
}

// crockfordChars is the set of uppercase Crockford base32 characters.
const crockfordChars = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

func isCrockfordBase32(s string) bool {
	for _, c := range s {
		if !strings.ContainsRune(crockfordChars, c) {
			return false
		}
	}
	return true
}

func TestNew_PrefixCorrectness(t *testing.T) {
	for _, prefix := range validPrefixes {
		got := ulid.New(prefix)
		if !strings.HasPrefix(got, prefix) {
			t.Errorf("New(%q) = %q, want prefix %q", prefix, got, prefix)
		}
	}
}

func TestNew_BodyLength(t *testing.T) {
	for _, prefix := range validPrefixes {
		got := ulid.New(prefix)
		body := strings.TrimPrefix(got, prefix)
		if len(body) != 26 {
			t.Errorf("New(%q) body length = %d, want 26; full value: %q", prefix, len(body), got)
		}
		if !isCrockfordBase32(body) {
			t.Errorf("New(%q) body %q contains non-Crockford chars", prefix, body)
		}
	}
}

func TestNew_MonotonicallyIncreasing(t *testing.T) {
	const n = 100
	ids := make([]string, n)
	for i := range ids {
		ids[i] = ulid.New("agent_")
	}
	// All distinct
	seen := make(map[string]bool, n)
	for _, id := range ids {
		if seen[id] {
			t.Errorf("duplicate ULID generated: %q", id)
		}
		seen[id] = true
	}
	// Lexicographically increasing
	for i := 1; i < n; i++ {
		if ids[i] <= ids[i-1] {
			t.Errorf("ULIDs not monotonically increasing at index %d: %q <= %q", i, ids[i], ids[i-1])
		}
	}
}

func TestNew_InvalidPrefix_Panics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Error("New(\"invalid_\") did not panic")
		}
	}()
	ulid.New("invalid_")
}
