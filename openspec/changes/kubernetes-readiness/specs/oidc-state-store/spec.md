# OIDC State Store

## ADDED Requirements

### Requirement: OIDC login state is persisted in a shared TTL'd store
The admin-api SHALL persist OIDC PKCE login state (`state`, `code_verifier`, `redirect_uri`) in a shared store (Postgres table `oidc_login_state`) rather than in process memory, with an expiry of `MINTKEY_OIDC_STATE_TTL_SECONDS` (default 600). State MUST be single-use: consumed (deleted) on callback.

#### Scenario: Login completes across a restart / different replica
- **WHEN** an operator begins login (state written) and the callback is served by a different admin-api process/replica or after a restart
- **THEN** the state is resolved from the shared store and the auth-code flow completes successfully

#### Scenario: Expired state is rejected
- **WHEN** a callback presents a `state` whose `expires_at` has passed
- **THEN** the login is rejected and no session is issued

#### Scenario: State is single-use
- **WHEN** a valid `state` is used to complete a callback and the same `state` is presented again
- **THEN** the second attempt is rejected (the state was consumed)
