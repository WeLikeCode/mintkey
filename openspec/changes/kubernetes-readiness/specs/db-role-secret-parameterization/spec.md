# DB Role Secret Parameterization

## ADDED Requirements

### Requirement: Database role passwords are injected from secrets at migrate time
The Liquibase migration that sets application-role passwords SHALL take the password values from injected properties (`MINTKEY_DB_APP_PASSWORD`, `MINTKEY_DB_SUBSCRIBER_PASSWORD`) rather than embedding literals in the changelog. `DATABASE_URL` used by services MUST be composed from the same secret values.

#### Scenario: Role uses the injected password
- **WHEN** migrations run with `MINTKEY_DB_APP_PASSWORD` set to a non-default value
- **THEN** the `mintkey_app` role authenticates with that value and no plaintext password literal remains in the changelog

#### Scenario: Dev default preserved when unset
- **WHEN** the password properties are unset (local compose)
- **THEN** the `.env.example` dev defaults are applied and the existing compose loop is unchanged

#### Scenario: No secret in version control
- **WHEN** the changelog file `015-app-role-passwords.yaml` is inspected
- **THEN** it contains property references, not literal passwords
