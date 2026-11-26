# Spec Delta

## Purpose
Each stored credential carries an egress scope, `any` or `public`. For a `public` credential the egress proxy connects only to public network addresses, whatever the stored target's name resolves to when the request is made.

## ADDED Requirements

### Requirement: Refuse IPv6 forms that carry an IPv4 address — feedback FB-002
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Refuse IPv6 forms that carry an IPv4 address
- **WHEN** a public-scope credential's target resolves to an address in 64:ff9b::/96 (NAT64), 2002::/16 (6to4) or 2001::/32 (Teredo)
- **THEN** the proxy refuses the connection as not public and answers the same 502 as for any other non-public address
