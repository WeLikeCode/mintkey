package main

// Tests for FB-002 (proxy-public-egress-fix-1): a public-scope credential whose
// stored target is an address in 64:ff9b::/96 (NAT64), 2002::/16 (6to4) or
// 2001::/32 (Teredo) is refused with the same 502 answer as any other
// non-public address.
//
// Source: proxy-public-egress spec, "Refuse IPv6 forms that carry an IPv4
// address — feedback FB-002".

import (
	"net/http"
	"strings"
	"testing"

	vaultv1 "github.com/mintkey/mintkey/packages/go/vault/v1"
)

// TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83 pins FB-002 at the
// proxy: for a target literal in each of the three IPv4-embedding IPv6 ranges,
// the generic flow with scope public answers 502 with the same not-allowed body
// as any other non-public address. Each address embeds the private IPv4
// address 10.0.0.1.
func TestPublicScopeRefusesIPv4EmbeddingIPv6Targets_C_da414c83(t *testing.T) {
	cases := []struct {
		name   string
		target string
	}{
		{"NAT64 64:ff9b::/96", "http://[64:ff9b::a00:1]:9"},
		{"6to4 2002::/16", "http://[2002:a00:1::1]:9"},
		{"Teredo 2001::/32", "http://[2001:0:a00:1::1]:9"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rw := scopedGenericFlow(t, testHandler(), &vaultv1.GetCredentialResponse{
				AuthScheme: vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN,
				Value:      []byte(storedTargetTokenA),
				TargetUrl:  tc.target,
			}, "public")
			if rw.Code != http.StatusBadGateway {
				t.Fatalf("status = %d, want %d (body: %s)", rw.Code, http.StatusBadGateway, rw.Body.String())
			}
			if body := strings.TrimSpace(rw.Body.String()); body != "bad gateway: target address not allowed" {
				t.Fatalf("body = %q, want %q", body, "bad gateway: target address not allowed")
			}
		})
	}
}
