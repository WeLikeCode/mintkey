# Agent egress policy

## Purpose

The rule that decides whether a URL supplied by an agent may be used as a service target: public https addresses only,
checked by name and by every address the name resolves to.

## ADDED Requirements

### Requirement: Agent-supplied URLs must be public https targets
`mintkey_models.egress` (standard library only, `mypy --strict`) SHALL give:

```python
class TargetNotAllowed(Exception):   # .reason: not_https | userinfo_present | host_missing | host_invalid |
    reason: str                      #          ip_literal | denied_name | unresolvable | non_public_address
def egress_deny_names() -> tuple[str, ...]           # MINTKEY_AGENT_EGRESS_DENY, lower-cased, blanks dropped
def address_is_public(address: str) -> bool          # unwraps IPv4-mapped IPv6; global, not multicast; False for a
                                                     # string that is not an address (zone id, garbage)
async def resolve_host(host: str) -> list[str]       # the seam: loop.getaddrinfo; OSError on failure
async def check_agent_target_url(url: str) -> None   # calls resolve_host through the module
```

`check_agent_target_url(url)` SHALL raise `TargetNotAllowed` unless the scheme is `https`, there is no user info, and the
host (lower-cased, one trailing dot removed) is ASCII, not an IP literal, not `localhost`, contains a dot (a name without one
is `denied_name`), is not `*.internal`, `*.local` or an entry of `MINTKEY_AGENT_EGRESS_DENY` (comma-separated names or
`*.suffix`, any case), and resolves through `resolve_host` to a non-empty list of addresses that are all public
(`unresolvable`: the resolver raised `OSError` or returned nothing; a returned string that is not an address is
`non_public_address`). A `*.suffix` entry matches names that end in `.suffix`, never the bare suffix itself.
`MINTKEY_SSRF_ALLOW_PRIVATE` SHALL NOT affect it.

#### Scenario: refused URLs
- **WHEN** the check runs (`resolve_host` replaced) on `http://example.com/`, `https://u:p@example.com/`, `https:///x`,
  `https://exämple.com/`, `https://10.0.0.5/`, `https://[::1]/`, `https://93.184.216.34/`, `https://localhost/`,
  `https://intranet/`, `https://intranet./`, `https://localhost./`, `https://db.internal/`, `https://printer.local/`,
  `https://corp.example.com/` and `https://a.corp.example.net/` (deny variable `corp.example.com,*.corp.example.net`)
- **THEN** the reasons are `not_https`, `userinfo_present`, `host_missing`, `host_invalid`, `ip_literal` three times, then
  `denied_name` eight times

#### Scenario: names that resolve badly, and accepted URLs
- **WHEN** a valid-looking name resolves to `10.1.2.3`, `127.0.0.1`, `169.254.169.254`, `100.64.0.1`, `fc00::1`, `224.0.0.1`,
  `0.0.0.0`, `::ffff:10.0.0.1`, `fe80::1%eth0`, `not-an-address`, `["93.184.216.34", "10.0.0.1"]`, `[]`, or the resolver raises
  `OSError`; and `https://API.Example.com./v1`, `https://api.example.com:8443/v1?x=1` and `https://corp.example.net/` (deny
  variable `*.corp.example.net`) resolve to `93.184.216.34`
- **THEN** the reasons are `non_public_address` eleven times, then `unresolvable` twice; the three URLs pass; and
  `address_is_public` is true for `93.184.216.34` and `2606:2800:220:1:248:1893:25c8:1946` and false for `192.168.1.1`,
  `::1`, `100.64.0.1`, `fe80::1%eth0` and `nonsense`

#### Scenario: the deny list reader
- **WHEN** `egress_deny_names()` runs with the variable unset, `" Corp.Example.com , ,*.X.net"` and an empty string
- **THEN** the results are `()`, `("corp.example.com", "*.x.net")` and `()`
