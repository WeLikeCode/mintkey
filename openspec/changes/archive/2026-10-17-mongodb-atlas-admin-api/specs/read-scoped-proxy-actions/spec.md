# Read-Scoped Proxy Actions

## ADDED Requirements

### Requirement: The read:atlas action restricts the agent to safe HTTP methods
The egress proxy SHALL deny any upstream request whose JWT `scope` is `read:atlas` and whose HTTP method is not `GET`, `HEAD`, or `OPTIONS`, returning `403`. The `admin:atlas` action and all pre-existing actions (`call`, email scopes, etc.) SHALL be unaffected by this gate.

#### Scenario: read:atlas blocks a destructive method
- **WHEN** an agent holding a `read:atlas` token issues a `DELETE` through the proxy
- **THEN** the proxy returns `403` and does not contact the upstream

#### Scenario: read:atlas allows a safe method
- **WHEN** an agent holding a `read:atlas` token issues a `GET` through the proxy
- **THEN** the proxy proceeds with credential injection and forwards the request

#### Scenario: admin:atlas is unrestricted
- **WHEN** an agent holding an `admin:atlas` token issues a `POST` or `DELETE`
- **THEN** the proxy does not apply the read-only gate and proceeds normally

#### Scenario: Existing actions are unaffected
- **WHEN** an agent holding a `call`-scoped token (any existing service) issues any method
- **THEN** the proxy behaves exactly as before this change

### Requirement: Both Atlas actions are grantable and brokered end-to-end
An operator SHALL be able to grant an agent the `read:atlas` and/or `admin:atlas` action on an Atlas service, and `request_token` SHALL issue a JWT whose `scope` equals the requested action only when a matching permission grant exists.

#### Scenario: Token issued only for a granted action
- **WHEN** an agent requests a token for `read:atlas` on a service it was granted `read:atlas` on
- **THEN** the broker issues a JWT with `scope: read:atlas`; requesting an un-granted action returns `403 not_authorized`
