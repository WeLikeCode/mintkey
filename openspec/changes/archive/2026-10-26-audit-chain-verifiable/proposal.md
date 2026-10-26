# The audit chain verifies with the same hash its writer stores

## Why

Every audit event carries `prev_hash` and `hash`, with `hash = sha256(canonical_json(event) || prev_hash)` and the
first `prev_hash` of a tenant equal to `sha256("mintkey-audit-genesis-v1:" + tenant_id)` (ADR-0014.7). That makes the
trail tamper-evident only if a verifier can recompute the hash the writer stored. Today it cannot:

- The writer, `audit_emit` in `packages/python/mintkey-models/mintkey_models/audit.py`, hashes nine fields: `id`,
  `tenant_id`, `event_type`, `actor_id`, `actor_type`, `target_id`, `target_type`, `payload` and `at` (the UTC time it
  stores, as `datetime.isoformat()`).
- The verify job (`apps/audit-verify-job/verify.py`) and the endpoint `POST /v1/admin/audit/verify-chain`
  (`apps/admin-api/src/admin_api/api/audit_admin.py`) each re-implement the hash over three fields: `event_type`,
  `tenant_id` and `payload`.

So no event written by `audit_emit` verifies: every non-empty chain is reported broken at its first event, and a
real change to a stored event cannot be told apart from that noise. For a credential broker, whose audit trail is the
record of who obtained which credential, a check that cannot pass is no check. The endpoint also reads events in `id`
order (random UUIDs, not chain order) and would put the database's `UUID` objects into its JSON answer. The columns
`request_id` and `trace_id` are stored but not hashed, so a value written there would go unnoticed.

## What Changes

- A new module, `mintkey_models.audit_hash`, holds the one canonical form: the nine hashed fields, how each is
  serialised from its stored value (`at` in UTC through `isoformat()`, ids as canonical UUID text), the JSON
  serialisation, the chain step and the genesis hash. It is byte for byte the form `audit_emit` has always hashed;
  golden values pin it.
- `audit_emit` builds its hashed fields with that module; what it stores does not change.
- The verify job and the verify-chain endpoint read all 13 columns, use the same module, and follow the chain by its
  links (`prev_hash` to the previous `hash`), so the result does not depend on the order of the rows. An event whose
  `request_id` or `trace_id` is set fails, since the hash does not cover them and no writer sets them.
- Tests write events with `audit_emit` (no database), verify them from their stored form with the module, the job and
  the endpoint, and show that changing any one of the 13 stored columns fails the check.

## Capabilities

### New Capabilities
- `audit-chain`: how an audit event's hash is formed from its stored values, and how the verify job and the
  verify-chain endpoint check a tenant's chain with that form.

## Impact

- New module: `packages/python/mintkey-models/mintkey_models/audit_hash.py`.
- Changed: `packages/python/mintkey-models/mintkey_models/audit.py` (`compute_hash`, `audit_emit`),
  `apps/audit-verify-job/verify.py`, `apps/audit-verify-job/main.py`,
  `apps/admin-api/src/admin_api/api/audit_admin.py` (`verify_chain_endpoint`).
- New tests: `packages/python/mintkey-models/tests/test_audit_hash.py`,
  `tests/unit/admin_api/test_audit_verify_job_chain.py`, `tests/unit/admin_api/test_audit_verify_endpoint_chain.py`.
  Changed tests (set-up only): `tests/unit/admin_api/test_audit_verify_endpoint.py`,
  `tests/unit/audit_verify/test_chain_verify.py`.
- Stored events: no migration. The canonical form is the one every stored hash was computed with, so existing intact
  chains verify after the change. There is no hash version to add; a future change of the form would add one.
  `tests/acceptance/test_audit_chain.py` (Docker, run by the repository's CI), which recomputes hashes from rows
  stored in a real Postgres with `compute_hash`, keeps passing: that function's result does not change.
- Operators: after the upgrade, a verify result is meaningful: ok means the tenant's chain is intact; a failure names
  the first event that does not verify and both hashes. Reports produced before the upgrade (every non-empty chain
  "broken") can be discarded. The verify job now imports `mintkey_models`: run it where that package is importable,
  e.g. `PYTHONPATH=packages/python/mintkey-models python apps/audit-verify-job/main.py` with the job's existing
  `DATABASE_URL`.
- API: the verify-chain answer keeps its shape (`docs/architecture/contracts/rest/openapi.yaml` already allows `null`
  hashes); ids in it are strings.
- Out of scope: checking the last event against `audit_chain_state.head_hash`; the genesis helpers in
  `admin_api.api.tenants` and the seed job (same value, unchanged); the unused Go `packages/go/audit.ComputeHash`
  (no production caller); hashing `request_id` or `trace_id`.

## Issue Intake (remediation gate)

1. **Problem statement**: the audit chain's verifiers hash different fields than its writer, so no stored event
   verifies.
2. **User-visible symptom**: `POST /v1/admin/audit/verify-chain` and the verify job report every non-empty tenant
   chain as broken at its first event.
3. **Expected behavior**: an event written by `audit_emit` verifies; changing any of its stored columns makes the
   check fail and name the event.
4. **Evidence**: the field lists in `audit.py` (`audit_emit`), `verify.py` (`compute_event_hash`) and
   `audit_admin.py` (`_compute_event_hash`); the existing verifier tests build their chains with the three-field
   formula, not with `audit_emit`.
5. **Scope**: the module, the writer's use of it, the two verifiers, and the tests above.
6. **Risk**: low. The writer's bytes and stored values do not change (golden test); the verifiers only read.
