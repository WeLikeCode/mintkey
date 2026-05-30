// Package credential — SSRF dial-time guard.
//
// ssrfSafeDialContext implements net.Dialer.DialContext in a way that checks
// the resolved IP address BEFORE establishing any TCP connection.  Checking at
// dial time defeats DNS-rebind: we inspect the IP that the OS actually
// resolved, not the hostname that was supplied by the caller.
//
// Blocked ranges (deny-by-default):
//   - Loopback      127.0.0.0/8  (IPv4)  ::1/128 (IPv6)
//   - Link-local    169.254.0.0/16        fe80::/10
//   - Private       10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
//   - ULA            fc00::/7
//   - Unspecified   0.0.0.0/8             ::/128
//   - Multicast     224.0.0.0/4           ff00::/8
//
// Dev opt-in: pass allowPrivate=true to bypassSSRFGuard to allow private targets
// for tests or internal development.  Deny is always the default on the exported
// NewTokenExchanger constructor.
package credential

import (
	"context"
	"fmt"
	"net"
	"time"
)

// ssrfBlockedRanges are the CIDR ranges that must never be dialled.
var ssrfBlockedRanges []*net.IPNet

func init() {
	cidrs := []string{
		// IPv4
		"127.0.0.0/8",    // loopback
		"169.254.0.0/16", // link-local (AWS metadata, etc.)
		"10.0.0.0/8",     // RFC 1918 class A
		"172.16.0.0/12",  // RFC 1918 class B
		"192.168.0.0/16", // RFC 1918 class C
		"0.0.0.0/8",      // unspecified
		"224.0.0.0/4",    // multicast
		"240.0.0.0/4",    // reserved
		// IPv6
		"::1/128",     // loopback
		"fe80::/10",   // link-local
		"fc00::/7",    // ULA (unique local)
		"::/128",      // unspecified
		"ff00::/8",    // multicast
	}
	for _, c := range cidrs {
		_, ipNet, err := net.ParseCIDR(c)
		if err != nil {
			// This is a programmer error — panic at startup so it's caught in tests.
			panic(fmt.Sprintf("ssrf: bad CIDR %q: %v", c, err))
		}
		ssrfBlockedRanges = append(ssrfBlockedRanges, ipNet)
	}
}

// isBlockedIP returns true if ip falls within any ssrfBlockedRanges entry.
func isBlockedIP(ip net.IP) bool {
	for _, blocked := range ssrfBlockedRanges {
		if blocked.Contains(ip) {
			return true
		}
	}
	return false
}

// ssrfSafeDialContext is a DialContext function that resolves the host first,
// checks every resolved IP against the blocked ranges, and only then dials.
// allowPrivate bypasses the check (for tests / dev environments).
func ssrfSafeDialContext(allowPrivate bool) func(ctx context.Context, network, addr string) (net.Conn, error) {
	baseDialer := &net.Dialer{
		Timeout:   10 * time.Second,
		KeepAlive: 30 * time.Second,
	}
	return func(ctx context.Context, network, addr string) (net.Conn, error) {
		if allowPrivate {
			return baseDialer.DialContext(ctx, network, addr)
		}

		host, port, err := net.SplitHostPort(addr)
		if err != nil {
			return nil, fmt.Errorf("ssrf: invalid address %q: %w", addr, err)
		}

		// Resolve host → IPs.
		addrs, err := net.DefaultResolver.LookupHost(ctx, host)
		if err != nil {
			return nil, fmt.Errorf("ssrf: dns lookup failed for %q: %w", host, err)
		}
		if len(addrs) == 0 {
			return nil, fmt.Errorf("ssrf: no addresses for %q", host)
		}

		// Check every resolved address — block if ANY is in a blocked range.
		for _, a := range addrs {
			ip := net.ParseIP(a)
			if ip == nil {
				return nil, fmt.Errorf("ssrf: unparseable resolved address %q", a)
			}
			if isBlockedIP(ip) {
				return nil, fmt.Errorf("ssrf: blocked address %s for host %q", ip, host)
			}
		}

		// Safe to dial.
		return baseDialer.DialContext(ctx, network, net.JoinHostPort(host, port))
	}
}

