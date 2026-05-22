// Package egress_test exercises the egress redirect allowlist.
//
// Tests mirror the three scenarios from T-1.6.6:
//   1. 302 to a different origin → NOT allowed (Kong returns verbatim)
//   2. 302 to the same origin   → allowed (Kong may follow)
//   3. Relative redirect         → allowed by definition
//
// Source: T-1.6.6; Req 7 AC13; ADR-0007.
package egress_test

import (
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/egress"
)

func TestIsAllowedRedirect(t *testing.T) {
	registered := "https://api.example.com"

	tests := []struct {
		name     string
		location string
		want     bool
	}{
		// Scenario 1: cross-origin redirect — NOT allowed (ADR-0007 egress allowlist)
		{
			name:     "cross-origin http→https upgrade blocked",
			location: "https://evil.attacker.com/callback",
			want:     false,
		},
		{
			name:     "cross-origin different host blocked",
			location: "https://other-api.example.com/path",
			want:     false,
		},
		{
			name:     "cross-origin to plain http blocked",
			location: "http://api.example.com/path",
			want:     false,
		},
		// Scenario 2: same-origin redirect — allowed
		{
			name:     "same-origin absolute URL allowed",
			location: "https://api.example.com/health",
			want:     true,
		},
		{
			name:     "same-origin with path allowed",
			location: "https://api.example.com/v2/resource?foo=bar",
			want:     true,
		},
		// Scenario 3: relative redirect — same-origin by definition
		{
			name:     "relative redirect allowed",
			location: "/health",
			want:     true,
		},
		{
			name:     "relative redirect with query allowed",
			location: "/redirect?to=home",
			want:     true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := egress.IsAllowedRedirect(tc.location, registered)
			if got != tc.want {
				t.Errorf("IsAllowedRedirect(%q, %q) = %v, want %v",
					tc.location, registered, got, tc.want)
			}
		})
	}
}

func TestOrigin(t *testing.T) {
	tests := []struct {
		rawURL string
		want   string
	}{
		{"https://api.example.com/path", "https://api.example.com"},
		{"http://localhost:8080/health", "http://localhost:8080"},
		{"/relative", ""},
		{"", ""},
		{"not-a-url", ""},
	}
	for _, tc := range tests {
		got := egress.Origin(tc.rawURL)
		if got != tc.want {
			t.Errorf("Origin(%q) = %q, want %q", tc.rawURL, got, tc.want)
		}
	}
}
