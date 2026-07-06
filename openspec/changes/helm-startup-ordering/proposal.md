# Helm Startup Ordering — fix seed-job / Keycloak deadlock

## Why

Verified live on a real cluster: `helm install` on `deploy/helm/mintkey` deadlocks and never completes.

The **seed-job** (`templates/jobs/seed-job.yaml`) is a `pre-install,pre-upgrade` hook at weight `-4`. Its `wait-for-keycloak` init container blocks until `nc -z <release>-keycloak 8443` succeeds. But **Keycloak** (`templates/stateful/keycloak.yaml`) is an ordinary `StatefulSet` — a **main release resource**, not a hook. Helm's hook contract runs all `pre-install` hooks (and waits for them to reach a terminal state) **before** it renders/applies any main resource. So:

1. Helm starts the `pre-install` hooks in weight order: `bootstrap-secrets` PVC (`-6`) → `liquibase` Job (`-5`) → `seed-job` (`-4`).
2. `seed-job`'s `wait-for-keycloak` init container blocks forever, because Keycloak — a main resource — has not been created yet and will not be created until every `pre-install` hook (including `seed-job` itself) succeeds.
3. Result: permanent deadlock. `helm install --wait` times out; without `--wait` the release reports `deployed` while `seed-job` sits `Pending`/`Init` forever and never seeds the Keycloak realm, admin password, or OIDC client secrets.

This is compounded by `admin-api` and `admin-ui`, which mount the `bootstrap-secrets` volume that only `seed-job` populates (admin password, OIDC client secrets, the Keycloak realm import) — so even if the deadlock were papered over, those deployments have nothing valid to read until `seed-job` has actually run against a live Keycloak.

## What Changes

- **`templates/jobs/seed-job.yaml`**: change the Helm hook annotation from `"helm.sh/hook": pre-install,pre-upgrade` to `"helm.sh/hook": post-install,post-upgrade`. `seed-job` now runs *after* Helm has created and waited on all main resources (Keycloak, admin-api, admin-ui, kong, etc.), by which point Keycloak is a real, addressable Service and the existing `wait-for-keycloak` / `wait-for-liquibase` init containers resolve immediately instead of blocking forever.
- **Keycloak stays a main resource** (`StatefulSet`, not a hook) — no change to `templates/stateful/keycloak.yaml`. A long-running service does not belong in the hook lifecycle (see `design.md` for why).
- **`bootstrap-secrets` PVC stays a `pre-install,pre-upgrade` hook at weight `-6`** — no change. It must exist before *both* the main app pods (admin-api, admin-ui mount it at pod creation) and the now-post-install `seed-job` (which writes into it), so it still needs to be provisioned earliest, ahead of the main resources.
- **`liquibase` stays a `pre-install,pre-upgrade` hook at weight `-5`** — no change. DB schema still must exist before any main resource (including Keycloak, which uses the same Postgres) comes up.
- **Consequence to document, not to fix here**: on first install, `admin-api` and `admin-ui` come up as main resources *before* `seed-job` (now post-install) has written the OIDC client secrets and admin password into `bootstrap-secrets`. Those pods MAY crash-loop briefly (missing/incomplete secret file) until `seed-job` completes and populates the volume, at which point Kubernetes' normal restart/backoff cycle brings them up clean on a subsequent restart. This is acceptable for this pre-alpha chart and is called out in `design.md` rather than solved with additional init-container gating (which would reintroduce the same class of deadlock under `--wait`).

## Capabilities

### New Capabilities
- `helm-startup-ordering`: the Helm chart's install/upgrade ordering guarantees the seed-job runs only after Keycloak (and the rest of the main release) is up and reachable, so `helm install` completes without a hook deadlock and the chart's seeded state (admin password, OIDC client secrets, Keycloak realm) is reliably produced on every install and upgrade.

## Impact

- **Changed**: `deploy/helm/mintkey/templates/jobs/seed-job.yaml` — hook annotation only (`pre-install,pre-upgrade` → `post-install,post-upgrade`); no change to the Job's containers, env, or volumes.
- **Unchanged** (context, confirmed correct as-is): `templates/pvc/bootstrap-secrets.yaml` (pre-install hook, weight `-6`, RWX), `templates/jobs/liquibase.yaml` (pre-install hook, weight `-5`), `templates/stateful/keycloak.yaml` (main resource, not a hook).
- **Behavioral**: on a fresh install, `admin-api`/`admin-ui` may restart once or twice before their mounted `bootstrap-secrets` content is valid; this is expected and self-heals via normal Kubernetes pod restart backoff.
- **Out of scope**: gating `admin-api`/`admin-ui` on `seed-job` completion via an additional init container or wait mechanism — deliberately not done in this change (see `design.md` for why it would reintroduce a deadlock).

## Issue Intake (remediation gate)

1. **Problem statement**: The Helm chart deadlocks on `helm install` — the `seed-job` pre-install hook waits for Keycloak, but Keycloak is a main resource that Helm only creates after all pre-install hooks succeed.
2. **User-visible symptom**: `helm install`/`helm upgrade` never completes (`--wait` times out; without `--wait` the release reports success while `seed-job` is stuck `Init:0/2` forever and the Keycloak realm/admin password/OIDC secrets are never seeded).
3. **Expected behavior**: `helm install`/`helm upgrade` completes; `seed-job` transitions to `Completed` after Keycloak has been created and become reachable; no manual intervention required.
4. **Evidence**: reproduced live on a real cluster — `kubectl get pods` shows `seed-job`'s `wait-for-keycloak` init container looping `nc -z <release>-keycloak 8443` indefinitely while `kubectl get statefulset <release>-keycloak` shows the resource does not exist yet (Helm has not reached main-resource application because the `pre-install` hook phase, which includes `seed-job`, has not succeeded).
5. **Scope**: the `helm.sh/hook` annotation on `templates/jobs/seed-job.yaml` only.
6. **Out of scope**: making Keycloak a hook; gating `admin-api`/`admin-ui` startup on `seed-job` via extra init containers; any change to `liquibase.yaml` or `bootstrap-secrets.yaml` (already correct); any application code change.
7. **Risk level**: LOW — single hook-annotation change, scoped to chart metadata, does not touch container images, env vars, or application code. The documented app-restart-on-first-install behavior is a known, acceptable, self-healing side effect for this pre-alpha chart.
8. **Verification target**: the chart installs on a real cluster without deadlocking, and `seed-job` reaches `Completed` only after Keycloak is up and reachable (i.e., `kubectl get job <release>-seed-job` shows `Completed` and `kubectl logs` on the `wait-for-keycloak` init container shows it resolved promptly rather than looping indefinitely).
9. **Owner decisions**: accept the brief admin-api/admin-ui crash-loop-and-self-heal window on first install rather than adding init-container gating in this change (deferred, out of scope, see `design.md`).
