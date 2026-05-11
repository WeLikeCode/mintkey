// Package egress implements the egress redirect allowlist for the proxy plugin.
//
// Kong is configured with follow_redirects=false (see kong.yml template generated
// by kong-syncer). This package provides the helper used in the header_filter phase
// to classify 3xx Location headers as same-origin (allowed) or cross-origin (blocked).
//
// Source: T-1.6.6; Req 7 AC13; ADR-0007.
package egress

import (
	"net/url"
	"strings"
)

// Origin returns the scheme+host(:port) of a URL, lower-cased.
// Returns "" for invalid or relative URLs.
func Origin(rawURL string) string {
	if rawURL == "" {
		return ""
	}
	u, err := url.Parse(rawURL)
	if err != nil || u.Host == "" {
		return ""
	}
	return strings.ToLower(u.Scheme) + "://" + strings.ToLower(u.Host)
}

// IsAllowedRedirect returns true when the redirect target is considered the
// same origin as registeredBaseURL (i.e. Kong may follow it), and false when
// it is cross-origin (Kong must NOT follow — the 302 is returned verbatim to
// the agent).
//
// Relative URLs (no host) are considered same-origin.
// If registeredBaseURL cannot be parsed the function is conservative: returns false.
func IsAllowedRedirect(location, registeredBaseURL string) bool {
	locationOrigin := Origin(location)
	if locationOrigin == "" {
		// Relative redirect — same-origin by definition.
		return true
	}
	baseOrigin := Origin(registeredBaseURL)
	if baseOrigin == "" {
		// Cannot determine registered origin — reject for safety.
		return false
	}
	return locationOrigin == baseOrigin
}
