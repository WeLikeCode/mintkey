# Tasks: audit-chain-verifiable

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run the touched
suites, `ruff check` and `mypy --strict` (`packages/python/mintkey-models`: `mintkey_models/`; admin-api:
`src/admin_api/`).

Writing an event in a test (tasks 1.1, 2.1, 2.2), no database: a fake session class in the test file, whose `async
execute(statement, params=None)` answers the statement whose text contains `FROM audit_chain_state` with a result
whose `fetchone()` returns `(head,)`, records the parameters of the statement that starts with `INSERT INTO
audit_events`, sets `head` to the `hash` parameter of the statement that starts with `UPDATE audit_chain_state`, and
returns a `MagicMock()` for any other statement. `head` starts as `genesis_hash(str(tenant_id))`. The event is written
with `asyncio.run(audit_emit(session, tenant_id=<UUID>, event_type="service.created", actor_id=<UUID>,
actor_type="operator", target_id=None, target_type=None, payload={"name": "svc-a", "count": 2}))`. The stored row is a
`types.SimpleNamespace` built from the recorded INSERT parameters as Postgres returns them: `id`, `tenant_id`,
`actor_id` as `uuid.UUID` (or `None`), `target_id` `None`, `event_type`, `actor_type`, `target_type` as bound,
`payload` = `json.loads(params["payload"])`, `at` = the bound datetime, `prev_hash` and `hash` as bound,
`request_id` and `trace_id` `None`. Every test asserts the type of a result (`bytes`, `str`, `ChainResult`,
`VerifyResult`) before it reads it, so a stubbed function fails by assertion.

## 1. One canonical form, used by the writer

- [x] 1.1 Tests first, new file `packages/python/mintkey-models/tests/test_audit_hash.py`, and the new module
  `packages/python/mintkey-models/mintkey_models/audit_hash.py` with the names and signatures of the requirements
  "One canonical form for the audit event hash" and "The chain is verified from the stored columns by its links"
  (red stubs the module, green fills it in). Cover every scenario of those two requirements and of "Altering any
  stored field of an event fails its verification": the golden bytes and digests (literal values, not recomputed),
  `mintkey_models.audit.compute_hash` on the golden dict, the time and id forms, then the stored-row scenarios with
  events written by `audit_emit` as above (`test_altering_one_stored_field_fails` is parametrised over the 13
  columns with the values the scenario gives; the copy in the fork scenario is
  `dataclasses.replace(second, id=<new UUID text>)` with its `hash` set to `event_hash` of that replaced event). The
  golden-bytes and stored-row tests fail before the change (no module); the `compute_hash` test already holds and
  fails once `compute_hash` is stubbed. Then in `packages/python/mintkey-models/mintkey_models/audit.py`:
  `compute_hash` returns `chain_hash(canonical_json_bytes(event_dict), prev_hash)`, and `audit_emit` builds
  `event_fields` with `canonical_event_fields(event_id=event_id, tenant_id=tenant_id, event_type=event_type,
  actor_id=actor_id, actor_type=actor_type, target_id=target_id, target_type=target_type, payload=payload, at=now)`;
  its four `execute` calls, their order and the INSERT parameters stay as they are. The existing
  `packages/python/mintkey-models/tests/test_audit.py` passes unchanged.

## 2. The verifiers use it

- [x] 2.1 Tests first, new file `tests/unit/admin_api/test_audit_verify_job_chain.py`: put
  `<repo>/packages/python/mintkey-models`, `<repo>/apps/admin-api/src` and `<repo>/apps/audit-verify-job` on
  `sys.path` as `tests/unit/admin_api/test_audit_verify_endpoint.py` and `tests/unit/audit_verify/test_chain_verify.py`
  do, import `verify` by that name (`main.py` imports it so), and load `<repo>/apps/audit-verify-job/main.py` with
  `importlib.util.spec_from_file_location("audit_verify_job_main", ...)`. Cover the four scenarios of the
  requirement "The verify job checks a chain with the canonical form" with events written by `audit_emit` as above.
  For the `main.py` scenario, `monkeypatch` sets `DATABASE_URL` to `postgresql+asyncpg://unused` and replaces
  `sqlalchemy.ext.asyncio.create_async_engine` (which `_run` imports when it runs) by a function returning a fake
  engine: `begin()` is an async context manager yielding a connection whose `async execute(statement, params=None)`
  records `str(statement)` and returns a result whose `fetchall()` gives `[(tenant_uuid,)]` for a statement containing
  `FROM tenants` and the stored rows for one containing `FROM audit_events`; `async dispose()` does nothing; the test
  calls `asyncio.run(job_main._run(None))`. The scenarios fail before the change (`verify_rows` does not exist, the
  three-field hash does not match, and the events SELECT lacks the columns). Change the
  existing `tests/unit/audit_verify/test_chain_verify.py::test_intact_chain_returns_ok`,
  `::test_tampered_chain_detects_first_bad_event`, `::test_genesis_hash_verification`, `::test_genesis_hash_value` and
  `::test_empty_chain_is_ok` only in the file's set-up: also put `<repo>/packages/python/mintkey-models` on
  `sys.path`, and `_build_chain` passes `at=datetime(2026, 1, 1, tzinfo=timezone.utc)` to each `AuditEvent`; the
  test bodies stay. (That file is run by neither the L4 gate nor ci.yml; run it with
  `uv run --directory apps/admin-api pytest ../../tests/unit/audit_verify`.) Then rewrite
  `apps/audit-verify-job/verify.py` as the requirement says (import from `mintkey_models.audit_hash`; `AuditEvent`
  gains the seven fields with default `None`; `compute_event_hash`, `verify_chain` and the new `verify_rows` delegate
  to `event_hash`, `chain_event_from_row` and `verify_events`), and in `apps/audit-verify-job/main.py` select the
  literal of design.md (with `:tid`) and call `verify_rows(rows)` instead of building `AuditEvent`s; its logging and
  exit codes stay.

- [x] 2.2 Tests first, new file `tests/unit/admin_api/test_audit_verify_endpoint_chain.py`: build the app as
  `_create_test_app` in `tests/unit/admin_api/test_audit_verify_endpoint.py` does (the session's `execute` records
  `str(statement)` and returns a result whose `fetchall()` gives the stored rows), and cover the three scenarios of the requirement "The verify-chain
  endpoint checks a chain with the canonical form" with events written by `audit_emit` as above; the first fails
  before the change (the three-field hash does not match). Change the existing
  `tests/unit/admin_api/test_audit_verify_endpoint.py::test_verify_chain_ok`, `::test_verify_chain_tampered` and
  `::test_verify_chain_tenant_id_param` only through the file's helpers: `_build_chain_rows` returns
  `types.SimpleNamespace` rows with all 13 columns (`id` `f"audit_evt_{i:03d}"`, `actor_id` `None`, `actor_type`
  `"system"`, `target_id` and `target_type` `None`, `at` `datetime(2025, 1, 1, tzinfo=timezone.utc) +
  timedelta(seconds=i)`, `request_id` and `trace_id` `None`) hashed with `canonical_event_fields`,
  `canonical_json_bytes`, `chain_hash` and `genesis_hash` from `mintkey_models.audit_hash`, which replace the file's
  `_genesis_hash` and `_compute_event_hash`; the test bodies stay. Then in
  `apps/admin-api/src/admin_api/api/audit_admin.py`: remove `_GENESIS_PREFIX`, `_genesis_hash` and
  `_compute_event_hash` (and imports left unused), select the literal of design.md (with `:tenant_id`), and answer
  from `verify_events([chain_event_from_row(row) for row in rows])` as the requirement says (`.hex()` of each hash,
  `null` when it is `None`); keep the `emit_platform_admin_access` call before the read and the
  `from mintkey_models.audit import audit_emit` import.
