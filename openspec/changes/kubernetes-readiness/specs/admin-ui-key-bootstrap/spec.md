# Admin-UI Key Bootstrap

## ADDED Requirements

### Requirement: The admin-ui signing keypair is generated at bootstrap
The seed-job SHALL generate the admin-ui Ed25519 signed-request keypair (`admin_ui_private.pem` mode 0400, `admin_ui_public.pem`) into the bootstrap secrets store if it is absent, idempotently, using the existing ensure-secret-file mechanism.

#### Scenario: Keypair generated once and stable across reruns
- **WHEN** the seed-job runs against an environment with no admin-ui keypair, and then runs again
- **THEN** after the first run the keypair exists with `admin_ui_private.pem` at mode 0400, and the second run leaves it unchanged

### Requirement: Production enforces signed admin-ui writes
When `MINTKEY_ENV=production`, admin-api SHALL reject admin-ui write requests that are unsigned or carry an invalid signature; the dev-only unsigned-write fallback applies only when not in production.

#### Scenario: Unsigned write rejected in production
- **WHEN** an admin-ui write request without a valid signature reaches admin-api under `MINTKEY_ENV=production`
- **THEN** the request is rejected (401/403) and no state is mutated

#### Scenario: Dev loop unchanged
- **WHEN** the same unsigned write reaches admin-api when not in production
- **THEN** the existing dev behavior is preserved (write allowed), so the current dev/e2e loop is unbroken
