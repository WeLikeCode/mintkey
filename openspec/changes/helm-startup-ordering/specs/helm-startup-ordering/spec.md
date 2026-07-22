# Helm Startup Ordering

## ADDED Requirements

### Requirement: seed-job runs as a post-install/post-upgrade hook, after Keycloak is reachable
The Helm chart SHALL run `seed-job` as a `post-install,post-upgrade` hook, so it is created only after Helm has applied all main release resources (including the Keycloak `StatefulSet`), and its `wait-for-keycloak` init container resolves against a Keycloak that already exists as an addressable Service rather than one Helm has not yet created.

#### Scenario: seed-job's wait-for-keycloak resolves against a live Keycloak
- **WHEN** `helm install` (or `helm upgrade`) is run and Helm proceeds through the release lifecycle
- **THEN** the Keycloak `StatefulSet` and Service exist and are addressable before the `seed-job` post-install hook is created, and the `wait-for-keycloak` init container's `nc -z <release>-keycloak 8443` check succeeds promptly instead of polling indefinitely

#### Scenario: bootstrap-secrets PVC still precedes both consumers
- **WHEN** the chart installs
- **THEN** the `bootstrap-secrets` PVC (a `pre-install` hook, weight `-6`) is provisioned before the main `admin-api`/`admin-ui` Deployments mount it and before the post-install `seed-job` writes into it

### Requirement: helm install/upgrade completes without a hook-ordering deadlock
The chart SHALL NOT contain a pre-install (or pre-upgrade) hook that depends on the readiness of a main release resource, since Helm does not apply main resources until all pre-install/pre-upgrade hooks have reached a terminal success state.

#### Scenario: Fresh install completes end to end
- **WHEN** an operator runs `helm install mintkey deploy/helm/mintkey -f values.yaml` (with required Secrets pre-created) against an empty namespace
- **THEN** the install completes (with or without `--wait`, within a bounded timeout) — the `bootstrap-secrets` PVC and `liquibase` Job (pre-install hooks) succeed first, the main resources (Keycloak, admin-api, admin-ui, kong, etc.) are created and become Ready, and the `seed-job` post-install hook then reaches `Completed`

#### Scenario: No resource has a hook phase that requires a not-yet-created resource
- **WHEN** every template's `helm.sh/hook` annotation and its runtime dependencies (init containers, env-derived hostnames) are inspected
- **THEN** no `pre-install`/`pre-upgrade` hook depends on the readiness of any resource that is itself a main (non-hook) resource created later in the same phase ordering

### Requirement: seed-job is idempotent across repeated post-install/post-upgrade runs
The chart's `seed-job` SHALL be safe to re-run on every `helm upgrade` (and on a retried `helm install`), producing no duplicate or conflicting Keycloak realm, OIDC client, or `bootstrap-secrets` state when the seeded artifacts already exist.

#### Scenario: helm upgrade re-runs seed-job without error
- **WHEN** `helm upgrade` is run against an already-seeded release (Keycloak realm, OIDC clients, and `bootstrap-secrets` files already populated by a prior install)
- **THEN** the `post-upgrade` `seed-job` hook re-runs and completes successfully, leaving the existing realm, OIDC client secrets, and `bootstrap-secrets` files unchanged (no duplicate-resource errors, no secret rotation as a side effect of re-seeding)

#### Scenario: Retried install after a transient failure does not duplicate state
- **WHEN** a `helm install` is retried after the `seed-job` post-install hook previously ran partially or fully (e.g. after a transient failure and hook redelivery per `hook-delete-policy: before-hook-creation`)
- **THEN** the re-run `seed-job` completes without creating duplicate Keycloak realms/clients or corrupting previously written `bootstrap-secrets` files
