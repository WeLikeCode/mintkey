# Proposal: fix 1 for proxy-public-egress

## Why
Requested by CiprianSpot, 2026-11-26T16:06:09Z in FB-001 (refactor, apps/proxy-plugin/internal/egress/public.go:112-123): PublicDialContext assigns the captured r and d inside the returned closure when they are nil. NewPublicTransport passes r = nil and shares one transport across requests, so concurrent first dials write the captured variable at the same time (a data race the race detector reports). Pick net.DefaultResolver and a zero Dialer once, before the closure is returned, and let the closure only read them. Behaviour is unchanged.

    func PublicDialContext(r Resolver, d *net.Dialer) func(ctx context.Context, network, addr string) (net.Conn, error) {
    	return func(ctx context.Context, network, addr string) (net.Conn, error) {
    		host, port, err := net.SplitHostPort(addr)
    		if err != nil {
    			return nil, fmt.Errorf("egress: split address %q: %w", addr, err)
    		}
    		if r == nil {
    			r = net.DefaultResolver
    		}
    		if d == nil {
    			d = &net.Dialer{}
    		}

Requested by CiprianSpot, 2026-11-26T16:06:16Z in FB-002 (behaviour): These IPv6 forms embed an IPv4 address, and the guard classifies them by their IPv6 prefix only, so an embedded private IPv4 address is not refused; the current list does not include them. Add the three ranges to nonPublicRanges in apps/proxy-plugin/internal/egress/public.go; every other address keeps its classification.

The verifier found problems in `proxy-public-egress` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-b58eac76 (major): Feedback FB-001 (refactor): Resolve the resolver and dialer defaults outside the dial closure
- F-3d836ff5 (major): Feedback FB-002 (behaviour): Refuse IPv6 forms that carry an IPv4 address

## Impact
The code and the tests of `proxy-public-egress`.
