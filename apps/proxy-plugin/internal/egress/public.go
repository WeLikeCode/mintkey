// Package egress — the connect-time public-egress guard (proxy-public-egress).
//
// A credential whose egress scope is anything other than the empty string or
// "any" may connect only to public network addresses, whatever the stored
// target's name resolves to when the request is made. PublicDialContext
// resolves the host, refuses any address that is not public, and dials the
// checked address literal — never the name — so a second lookup cannot send
// the connection elsewhere (DNS-rebind). NewPublicTransport wraps that dial
// function in an http.Transport whose Proxy is nil, so HTTP_PROXY cannot move
// the connection to an address the guard never sees.
//
// The ranges are the ones of the spec and are deliberately distinct from the
// dial-time guard of internal/credential/ssrf.go, which keeps covering the
// OAuth2 token exchanges (design D8).
//
// Source: proxy-public-egress (spec + design D2, D3, D4, D5).
package egress

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"time"
)

// ScopeAny and ScopePublic are the two egress scopes the vault adapter stores
// with a credential. The proxy treats every scope other than the empty string
// and ScopeAny as ScopePublic, so an unknown scope of a newer adapter can
// only make connections stricter, never looser (design D2).
const (
	ScopeAny    = "any"
	ScopePublic = "public"
)

// ErrTargetNotPublic is returned by PublicDialContext when a resolved address
// is not public. The reverse proxy's ErrorHandler answers it with the 502
// text of the spec; every other dial error (a failed lookup, an empty answer,
// a refused connection) is an unreachable upstream.
var ErrTargetNotPublic = errors.New("target address is not public")

// Resolver resolves a host name to its addresses. net.DefaultResolver
// satisfies it.
type Resolver interface {
	LookupIPAddr(ctx context.Context, host string) ([]net.IPAddr, error)
}

// nonPublicRanges are the ranges the guard refuses, parsed once at init.
// IPv4-mapped IPv6 addresses are unwrapped before the check, so no entry
// needs a v4-mapped form.
var nonPublicRanges = parseNonPublicRanges()

func parseNonPublicRanges() []*net.IPNet {
	cidrs := []string{
		// IPv4
		"0.0.0.0/8",      // unspecified (this network)
		"127.0.0.0/8",    // loopback
		"10.0.0.0/8",     // private
		"172.16.0.0/12",  // private
		"192.168.0.0/16", // private
		"169.254.0.0/16", // link-local
		"100.64.0.0/10",  // carrier-grade NAT
		"224.0.0.0/4",    // multicast
		"240.0.0.0/4",    // reserved (holds the broadcast address)
		// IPv6
		"::/128",    // unspecified
		"::1/128",   // loopback
		"fe80::/10", // link-local
		"fc00::/7",  // unique-local
		"ff00::/8",  // multicast
	}
	ranges := make([]*net.IPNet, 0, len(cidrs))
	for _, c := range cidrs {
		_, ipNet, err := net.ParseCIDR(c)
		if err != nil {
			// A programmer error — panic at startup so it is caught in tests.
			panic(fmt.Sprintf("egress: bad CIDR %q: %v", c, err))
		}
		ranges = append(ranges, ipNet)
	}
	return ranges
}

// IsPublicIP reports whether ip is a public address: not unspecified,
// loopback, private, link-local, carrier-grade NAT, unique-local, multicast
// or reserved. An IPv4-mapped IPv6 address is unwrapped first, so
// ::ffff:10.0.0.1 counts as 10.0.0.1. Everything else counts as public,
// including documentation and benchmarking ranges (design D4).
func IsPublicIP(ip net.IP) bool {
	if ip == nil {
		return false
	}
	if v4 := ip.To4(); v4 != nil {
		ip = v4
	}
	for _, n := range nonPublicRanges {
		if n.Contains(ip) {
			return false
		}
	}
	return true
}

// PublicDialContext returns a DialContext that splits addr, classifies an IP
// literal as it is, resolves a name with r (net.DefaultResolver when nil),
// returns an error that wraps ErrTargetNotPublic when any resolved address is
// not public, returns an error that does not wrap it when the lookup fails or
// answers no address, and otherwise dials net.JoinHostPort(ip.String(), port)
// of the checked addresses in order and returns the first success — never a
// second lookup of the name (design D3). d nil means a zero Dialer.
func PublicDialContext(r Resolver, d *net.Dialer) func(ctx context.Context, network, addr string) (net.Conn, error) {
	// Resolve the defaults once, before the closure is returned: the closure
	// may run concurrently (NewPublicTransport passes nil and shares one
	// transport across requests), so it must only read these values.
	if r == nil {
		r = net.DefaultResolver
	}
	if d == nil {
		d = &net.Dialer{}
	}
	return func(ctx context.Context, network, addr string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(addr)
		if err != nil {
			return nil, fmt.Errorf("egress: split address %q: %w", addr, err)
		}

		var ips []net.IPAddr
		if ip := net.ParseIP(host); ip != nil {
			// An IP literal is classified as it is.
			ips = []net.IPAddr{{IP: ip}}
		} else {
			ips, err = r.LookupIPAddr(ctx, host)
			if err != nil {
				return nil, fmt.Errorf("egress: lookup %q: %w", host, err)
			}
			if len(ips) == 0 {
				return nil, fmt.Errorf("egress: lookup %q: no addresses", host)
			}
		}

		// Every resolved address is checked before one is dialled: a name
		// that answers a public and a non-public address is refused.
		for _, ia := range ips {
			if !IsPublicIP(ia.IP) {
				return nil, fmt.Errorf("%w: %s resolves to %s", ErrTargetNotPublic, host, ia.IP)
			}
		}

		var lastErr error
		for _, ia := range ips {
			conn, dialErr := d.DialContext(ctx, network, net.JoinHostPort(ia.IP.String(), port))
			if dialErr == nil {
				return conn, nil
			}
			lastErr = dialErr
		}
		return nil, lastErr
	}
}

// NewPublicTransport returns a clone of http.DefaultTransport that dials
// through PublicDialContext and takes no proxy from the environment (design
// D5). The transport pools connections, so it is meant to be created once per
// handler and shared.
func NewPublicTransport() *http.Transport {
	t := http.DefaultTransport.(*http.Transport).Clone()
	t.Proxy = nil
	t.DialContext = PublicDialContext(nil, &net.Dialer{
		Timeout:   30 * time.Second,
		KeepAlive: 30 * time.Second,
	})
	return t
}
