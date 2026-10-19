# Design — Helm Startup Ordering

> **Status:** Proposed — 2026-07-06
> **Branch:** `fix/helm-kong-syncer-admin-url`
> **Canonical plan:** this folder (`proposal.md` + `specs/` + `tasks.md`)
> **Origin:** live deadlock reproduced on a real cluster while validating `deploy/helm/mintkey`; this document records the ordering fix and the alternatives rejected.

## 1. Goal

Make `helm install`/`helm upgrade` complete without deadlocking, by moving `seed-job` out of the `pre-install` hook phase (where it cannot reach Keycloak) into `post-install`/`post-upgrade` (where Keycloak already exists and is reachable). No change to Keycloak's resource kind, no change to `liquibase` or the `bootstrap-secrets` PVC, no application code change.

## 2. Why it deadlocks today

Helm's hook contract (see Helm docs on hook lifecycle) processes a release in three ordered phases:

1. **Pre-install/pre-upgrade hooks** — created and waited on for a terminal state, in ascending `helm.sh/hook-weight` order, *before* anything else.
2. **Main release resources** — everything in `templates/` that is not annotated as a hook (Deployments, StatefulSets, Services, etc.) — rendered and applied only after step 1 fully succeeds.
3. **Post-install/post-upgrade hooks** — created and waited on *after* step 2's resources exist (Helm does not block on their readiness by default, only their existence having been submitted — but they can themselves wait on main-resource readiness at the pod level, which is exactly what `seed-job`'s init containers already do).

Today's ordering:

| Phase | Resource | Weight | Status before fix |
|---|---|---|---|
| pre-install | `bootstrap-secrets` PVC | `-6` | OK — no dependency, provisions first |
| pre-install | `liquibase` Job | `-5` | OK — only needs Postgres, which is chart-managed and can be a main resource reachable independently, or is itself sequenced correctly today |
| pre-install | `seed-job` | `-4` | **Deadlocks** — its `wait-for-keycloak` init container polls `nc -z <release>-keycloak 8443`, but Keycloak is a *main resource*, not yet created because phase 1 (pre-install hooks) has not finished — `seed-job` itself is still running |
| main | Keycloak (`StatefulSet`), admin-api, admin-ui, kong, ... | n/a | Never reached — Helm will not proceed to phase 2 until phase 1's `seed-job` reports success |

`seed-job` waiting on a resource that can only exist once `seed-job` succeeds is a circular dependency. It cannot be broken by reordering hook weights within `pre-install` — Keycloak isn't in that phase at all.

## 3. The fix — move seed-job to post-install/post-upgrade

Change only the hook annotation on `templates/jobs/seed-job.yaml`:

```yaml
annotations:
  "helm.sh/hook": post-install,post-upgrade   # was: pre-install,pre-upgrade
  "helm.sh/hook-weight": "-4"                  # unchanged; weight ordering among post hooks doesn't matter here (seed-job is the only post hook), kept for continuity
  "helm.sh/hook-delete-policy": before-hook-creation
```

New ordering:

| Phase | Resource | Weight | Status after fix |
|---|---|---|---|
| pre-install | `bootstrap-secrets` PVC | `-6` | unchanged — provisions before anything mounts it |
| pre-install | `liquibase` Job | `-5` | unchanged — schema exists before any main resource that touches the DB |
| main | Keycloak (`StatefulSet`), admin-api, admin-ui, kong, kong-syncer, etc. | n/a | Helm creates and (with `--wait`) waits for these to become Ready |
| post-install | `seed-job` | `-4` | Runs *after* Keycloak exists as a Service — `wait-for-keycloak`'s `nc -z` resolves promptly instead of polling a resource that doesn't exist |

The chain end-to-end: **`bootstrap-secrets` PVC (pre-install, -6) → `liquibase` (pre-install, -5) → [main: Keycloak + admin-api + admin-ui + kong + ...] → `seed-job` (post-install)**.

`bootstrap-secrets` staying a `pre-install` hook is still correct and necessary post-fix: both the main app pods (admin-api/admin-ui, which mount it at pod-creation time in phase 2) and the now-post-install `seed-job` (which writes into it in phase 3) need the PVC to already exist by the time they start — so it must remain the earliest thing provisioned, not move alongside `seed-job`.

## 4. Why NOT make Keycloak a hook

Rejected. A Helm hook is a run-to-completion or ephemeral-lifecycle resource (Job/Pod, or a resource explicitly deleted per `hook-delete-policy`) — Helm's hook weight/wait semantics are built around "this exists to run once around the install/upgrade transaction," not "this is a long-running service the rest of the app talks to for the life of the release." Keycloak is a `StatefulSet` backing an always-on OIDC provider that admin-api, admin-ui, and every future consumer talk to continuously, including well after install — it needs standard Deployment/StatefulSet lifecycle (rolling updates, `helm upgrade` reconciliation, being a normal Service target), not hook semantics. Treating it as a hook would also mean it disappears from `helm get manifest`'s normal resource view and interacts oddly with `helm uninstall`/hook-delete-policy. Keeping it a main resource is the only fit for what it actually is.

## 5. Why NOT gate admin-api/admin-ui on seed-job via extra init containers

Rejected for this change (deliberately out of scope; noted in `proposal.md`). Adding a `wait-for-seed-job` init container to admin-api/admin-ui would reintroduce the same deadlock class: those Deployments are main resources, and if `helm install --wait` (or a readiness-based rollout) blocks the release on their pods becoming Ready, and their pods block on a **post-install** hook that Helm hasn't created yet (it runs *after* main resources are submitted), the wait can never resolve within the same `--wait` timeout envelope depending on how the wait is expressed, and at minimum reintroduces a second ordering dependency to reason about for no strong benefit here. The chosen tradeoff — accept a brief, self-healing crash-loop on first install — is simpler, matches the pre-alpha maturity of this chart, and keeps the fix to a single-line hook-annotation change. If this needs tightening later (e.g., before a GA chart), the better lever is a `helm upgrade --wait` in a two-step install runbook (main resources, confirm seed-job Completed, then bring up dependents) or a readiness gate on the secret file's mtime — not an init container that recreates the pre-install ordering problem.

## 6. What this change deliberately does NOT do

- Does not change `templates/pvc/bootstrap-secrets.yaml` (stays `pre-install`, weight `-6`, RWX).
- Does not change `templates/jobs/liquibase.yaml` (stays `pre-install`, weight `-5`).
- Does not change `templates/stateful/keycloak.yaml`'s resource kind or ordering.
- Does not add any init-container gating between `seed-job` and `admin-api`/`admin-ui`.
- Does not touch the already-fixed-on-this-branch items (liquibase image, liquibase `JAVA_OPTS` changelog params, `bootstrap-secrets` PVC RWX, seed-job init using `postgres:16`, kong-syncer → `-kong-admin:8001`).

## 7. Verification (the checks that prove the fix)

| Check | Expected result |
|---|---|
| `helm template deploy/helm/mintkey` after the change | `templates/jobs/seed-job.yaml` renders with `"helm.sh/hook": post-install,post-upgrade` |
| Fresh `helm install` on a real cluster | Completes (no `--wait` timeout); `kubectl get statefulset <release>-keycloak` exists and is Ready before `kubectl get job <release>-seed-job` is created |
| `kubectl get job <release>-seed-job` after install | Reaches `Completed`; `kubectl logs job/<release>-seed-job -c wait-for-keycloak` shows immediate resolution, not an indefinite retry loop |
| `admin-api`/`admin-ui` pods during first install | May show one or more restarts (`RESTARTS > 0`) before `seed-job` completes; stabilize to `Running`/`Ready` afterward without manual intervention |
| `helm upgrade` on an already-seeded release | `seed-job` re-runs as a `post-upgrade` hook and completes idempotently (no duplicate realm/client/secret creation errors) |
