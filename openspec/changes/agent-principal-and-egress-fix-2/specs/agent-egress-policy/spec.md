# Spec Delta

## Purpose
The rule that decides whether a URL supplied by an agent may be used as a service target: public https addresses only, checked by name and by every address the name resolves to.

## ADDED Requirements

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
