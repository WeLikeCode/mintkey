package egress

// Tests for FB-002 (proxy-public-egress-fix-1): three IPv6 ranges embed an
// IPv4 address, and the guard must refuse them as not public instead of
// classifying them by their IPv6 prefix only.
//
// Source: proxy-public-egress spec, "Refuse IPv6 forms that carry an IPv4
// address — feedback FB-002".

import (
	"context"
	"errors"
	"net"
	"testing"
	"time"
)

// staticResolver answers every lookup with the same addresses, so a test can
// exercise the "resolves to" half of the guard without relying on DNS.
type staticResolver []net.IPAddr

func (s staticResolver) LookupIPAddr(context.Context, string) ([]net.IPAddr, error) {
	return []net.IPAddr(s), nil
}

// TestPublicDialContextRefusesIPv4EmbeddingIPv6_C_da414c83 pins FB-002: a
// public credential's target that resolves to an address in 64:ff9b::/96
// (NAT64), 2002::/16 (6to4) or 2001::/32 (Teredo) is refused as not public
// instead of being dialled. Each range is checked with an address that embeds
// the private IPv4 address 10.0.0.1. The dialer has a short timeout so that a
// guard that lets the address through fails fast on the dial instead of
// waiting for a network timeout.
func TestPublicDialContextRefusesIPv4EmbeddingIPv6_C_da414c83(t *testing.T) {
	cases := []struct {
		name string
		ip   string
	}{
		{"NAT64 64:ff9b::/96", "64:ff9b::a00:1"},
		{"6to4 2002::/16", "2002:a00:1::1"},
		{"Teredo 2001::/32", "2001:0:a00:1::1"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			dial := PublicDialContext(
				staticResolver{{IP: net.ParseIP(tc.ip)}},
				&net.Dialer{Timeout: 100 * time.Millisecond},
			)
			conn, err := dial(context.Background(), "tcp", "rebind.test:9")
			if conn != nil {
				_ = conn.Close()
			}
			if !errors.Is(err, ErrTargetNotPublic) {
				t.Fatalf("dial error = %v, want an error wrapping ErrTargetNotPublic", err)
			}
		})
	}
}
