# agent-egress-policy Specification

## Purpose
The rule that decides whether a URL supplied by an agent may be used as a service target: public https addresses only,
checked by name and by every address the name resolves to.

## Requirements

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

### Requirement: Refuse the IPv6 forms that carry an IPv4 address — feedback FB-001
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Refuse the IPv6 forms that carry an IPv4 address
- **WHEN** an agent-supplied base_url or openapi_url names a host that resolves to an address in 64:ff9b::/96 (NAT64), 2002::/16 (6to4) or 2001::/32 (Teredo)
- **THEN** the check refuses it with mintkey:target_not_allowed, on every supported Python version, so the create-time check refuses every range the proxy's connect-time guard refuses

### Requirement: A malformed agent-supplied URL is refused, never an error — feedback FB-002
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: A malformed agent-supplied URL is refused, never an error
- **WHEN** an agent-supplied URL's host has an empty label or a label longer than 63 characters, or the URL contains whitespace, a tab, a newline, any other control character, a percent sign or a backslash, or the host's last label is all decimal digits or 0x-hexadecimal
- **THEN** the check refuses it with mintkey:target_not_allowed and no unhandled exception reaches the caller

### Requirement: The deny list matches names however they are written — feedback FB-003
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: The deny list matches names however they are written
- **WHEN** the host or a MINTKEY_AGENT_EGRESS_DENY entry ends in one or more dots, or the host is localhost or under .localhost, or an entry can never match a name (`*`, `*.`, a leading dot, `*name` without a dot)
- **THEN** a host matches a deny entry exactly as the same name without its trailing dots, localhost and any name under .localhost are refused, and an entry that can never match is reported once in the log as ignored
