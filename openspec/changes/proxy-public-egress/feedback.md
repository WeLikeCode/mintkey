# Feedback — proxy-public-egress

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | addressed | refactor | apps/proxy-plugin/internal/egress/public.go:112 | Resolve the resolver and dialer defaults outside the dial closure |
| FB-002 | addressed | behaviour |  | Refuse IPv6 forms that carry an IPv4 address |
<!-- l4:feedback-index:end -->

---

## FB-001: Resolve the resolver and dialer defaults outside the dial closure

- **Status:** addressed
- **Kind:** refactor
- **Where:** `apps/proxy-plugin/internal/egress/public.go:112-123`
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-26T16:06:09Z

### Code
```go
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
```

### Feedback
PublicDialContext assigns the captured r and d inside the returned closure when they are nil. NewPublicTransport passes r = nil and shares one transport across requests, so concurrent first dials write the captured variable at the same time (a data race the race detector reports). Pick net.DefaultResolver and a zero Dialer once, before the closure is returned, and let the closure only read them. Behaviour is unchanged.

### Outcome
<!-- written by the harness -->
Addressed in round 3 at 630ef8c953: public.go: defaults r/d resolved before returning the closure (`if r == nil { r = net.DefaultResolver }` outside closure).

---

## FB-002: Refuse IPv6 forms that carry an IPv4 address

- **Status:** addressed
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-26T16:06:16Z

### Feedback
These IPv6 forms embed an IPv4 address, and the guard classifies them by their IPv6 prefix only, so an embedded private IPv4 address is not refused; the current list does not include them. Add the three ranges to nonPublicRanges in apps/proxy-plugin/internal/egress/public.go; every other address keeps its classification.

### When / Then
- **When:** a public-scope credential's target resolves to an address in 64:ff9b::/96 (NAT64), 2002::/16 (6to4) or 2001::/32 (Teredo)
- **Then:** the proxy refuses the connection as not public and answers the same 502 as for any other non-public address

### Outcome
<!-- written by the harness -->
Addressed in round 3 at 630ef8c953: public.go nonPublicRanges adds 64:ff9b::/96, 2002::/16, 2001::/32.
