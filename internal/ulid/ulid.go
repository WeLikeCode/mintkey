// Package ulid generates prefixed ULIDs for Mintkey wire IDs.
//
// Every ID on the wire is a stable prefix (e.g. "tenant_", "agent_") followed
// by a 26-character Crockford base32 ULID body, satisfying ADR-0017.11.
package ulid

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"

	oklogulid "github.com/oklog/ulid/v2"
)

// validPrefixes is the closed set of allowed prefixes (ADR-0017.11).
var validPrefixes = map[string]struct{}{
	"tenant_":   {},
	"operator_": {},
	"agent_":    {},
	"svc_":      {},
	"cred_":     {},
	"perm_":     {},
	"audit_":    {},
	"change_":   {},
	"session_":  {},
	"system_":   {},
	"jti_":      {},
	"kid_":      {},
}

// monotonic entropy source ensures ULIDs generated in the same millisecond
// are still lexicographically increasing.
var (
	mu      sync.Mutex
	entropy = oklogulid.Monotonic(rand.Reader, 0)
)

// New returns a prefixed ULID string of the form "<prefix><26-char-body>".
// It panics if prefix is not in the valid set defined by ADR-0017.11.
func New(prefix string) string {
	if _, ok := validPrefixes[prefix]; !ok {
		panic(fmt.Sprintf("ulid: invalid prefix %q; must be one of the ADR-0017.11 set", prefix))
	}
	mu.Lock()
	id := oklogulid.MustNew(oklogulid.Timestamp(time.Now()), entropy)
	mu.Unlock()
	return prefix + id.String()
}
