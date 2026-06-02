package security

import (
	"fmt"
	"strings"
)

// AllowDomain checks whether addr.Domain is permitted by the provided
// allowedDomains list.
//
// Rules:
//   - Empty allowedDomains means "allow all" (operator opt-in open relay).
//   - Matching is case-insensitive.
//   - Entries may use a leading wildcard prefix: "*.example.com" matches
//     "sub.example.com" but NOT "example.com" (require at least one label
//     before the wildcard parent).
//   - Wildcard entries with no parent (e.g. "*.com") match only direct
//     single-label children (i.e. "foo.com") to prevent over-broad allowlists.
func AllowDomain(addr Addr, allowedDomains []string) error {
	if len(allowedDomains) == 0 {
		// Empty allowlist = operator has opted in to allow all domains.
		return nil
	}

	needle := strings.ToLower(addr.Domain)
	for _, pattern := range allowedDomains {
		if matchDomainPattern(needle, strings.ToLower(pattern)) {
			return nil
		}
	}
	return fmt.Errorf("security/allowlist: domain %q is not in the allowed list", addr.Domain)
}

// matchDomainPattern reports whether domain matches pattern.
// pattern may be:
//   - an exact domain:  "example.com"
//   - a wildcard:       "*.example.com"  (matches one extra label)
func matchDomainPattern(domain, pattern string) bool {
	if !strings.HasPrefix(pattern, "*.") {
		return domain == pattern
	}
	// Strip the leading "*."
	parent := pattern[2:]
	if !strings.HasSuffix(domain, "."+parent) {
		return false
	}
	// The subdomain part is everything before ".{parent}".
	sub := domain[:len(domain)-len(parent)-1]
	// Only allow a single label (no dots) in the wildcard position,
	// preventing *.example.com from matching a.b.example.com.
	return !strings.Contains(sub, ".")
}
