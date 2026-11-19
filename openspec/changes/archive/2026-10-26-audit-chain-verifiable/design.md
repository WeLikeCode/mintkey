# Design: audit-chain-verifiable

## Context

`audit_events` has 13 columns (`apps/admin-api/db/changelog/007-audit-events.yaml`): `id`, `tenant_id`, `event_type`,
`actor_id`, `actor_type`, `target_id`, `target_type`, `payload` (JSONB), `prev_hash`, `hash` (BYTEA), `request_id`,
`trace_id` and `at` (TIMESTAMPTZ). The only code that inserts into it is `audit_emit`
(`packages/python/mintkey-models/mintkey_models/audit.py`); admin-api and the MCP server call it, and the Go services
reach it through `POST /v1/internal/audit/emit`. `audit_emit` takes a per-tenant advisory lock, reads
`audit_chain_state.head_hash` (seeded with `sha256("mintkey-audit-genesis-v1:" + tenant_id)` by
`admin_api.api.tenants` and by the seed job), builds a dict of nine fields (`id`, `tenant_id`, `event_type`,
`actor_id`, `actor_type`, `target_id`, `target_type`, `payload`, `at` = `now.isoformat()` with
`now = datetime.now(timezone.utc)`), hashes it with `compute_hash` (`json.dumps(sort_keys=True,
separators=(",", ":"))`, then `sha256(canonical + prev_hash)`), inserts the row with `at = now` and `payload =
json.dumps(payload)`, and moves the head. It runs exactly four `session.execute` calls in that order; other tests
count them. `request_id` and `trace_id` are never bound, so they are NULL in every row.

Two verifiers recompute a different hash, over `event_type`, `tenant_id` and `payload` only:
`compute_event_hash` in `apps/audit-verify-job/verify.py` (used by `main.py`, which reads `ORDER BY at`) and
`_compute_event_hash` in `apps/admin-api/src/admin_api/api/audit_admin.py` (which reads `ORDER BY id`; the ids are
random UUIDs, so that is not chain order, and its JSON answer would hold the driver's `UUID` objects). Their tests
(`tests/unit/admin_api/test_audit_verify_endpoint.py`, `tests/unit/audit_verify/test_chain_verify.py`) build chains
with the same three-field formula, so they pass while no row written by `audit_emit` can verify.

`packages/go/audit` also has a `ComputeHash`, but nothing outside its own test imports the package and its `Emit`
returns "not yet wired": it writes nothing and is left as it is.

## Decisions

**D1. The canonical form is the writer's existing form; no migration and no hash version.** The writer's field set
and serialisation have not changed since `audit.py` was written (its git history shows the same nine fields and
`now.isoformat()`), so every stored row already carries a hash over that form. Choosing it means every existing
intact chain verifies after the change; choosing any other form would fail all of them or need a versioned hash and a
backfill. `GENESIS_PREFIX` already carries a version (`-v1`); a later change to the form must version it and is out
of scope. The golden scenario (fixed fields, fixed digest) pins the bytes so that a refactor cannot drift.

**D2. One module, used by all.** `mintkey_models.audit_hash` holds the form (standard library only: `hashlib`,
`json`, `dataclasses`, `datetime`, `uuid`, `typing`), so admin-api, the MCP server and the verify job import the same
code. `audit_emit` builds its dict with `canonical_event_fields(..., at=now)` and keeps `compute_hash`, which becomes
`chain_hash(canonical_json_bytes(event_dict), prev_hash)`; its four `execute` calls, their order and the INSERT
parameters do not change. `audit_admin.py` keeps `from mintkey_models.audit import audit_emit` (a test patches
`admin_api.api.audit_admin.audit_emit`).

**D3. Each field is serialised from what is stored.** `at` is `canonical_at(at)`: UTC, `datetime.isoformat()`. For
the writer's `now` this is the string it hashes today; for a value read back it is the same string whatever offset
the driver returns (asyncpg returns UTC; another driver may return the session's zone). TIMESTAMPTZ and `datetime`
both keep microseconds, so the stored value equals the hashed one. Ids go through `canonical_id`, so a `UUID` object
read back and the `str(uuid)` the writer hashed give the same text, and a non-UUID id (the existing tests use
`tenant_…` strings) passes unchanged. `payload` is hashed as the mapping; read back from JSONB it is the same JSON
object (keys sorted by the serialiser).

**D4. Verification follows the links, not a sort order.** `verify_events` starts at the genesis hash and moves to the
event whose `prev_hash` is the current hash. Sorting by `at` is not chain order when two admin-api replicas' clocks
differ, and sorting by `id` never is; following `prev_hash` needs no clock. Both SELECTs still use `ORDER BY at ASC,
id ASC`, so that the two verifiers name the same first bad event for the same rows. The walk is bounded by the number
of events. A fork (two events after one hash) leaves one of them unvisited and fails; so does a gap. The "first in
list order" rule keeps the existing expectations of `test_chain_verify.py` (a bad genesis link reports `evt_000`; a
changed payload at index 2 reports `evt_002` with `chain_length` 2).

**D5. `request_id` and `trace_id` must be NULL.** They are stored but not hashed, and no writer sets them. Rather than
change the hashed form (D1), a verifier refuses an event where either is set. If a writer starts setting them, it must
add them to the hashed form with a new version, and this check makes that impossible to miss.

**D6. The verify job keeps its interface.** `verify.py` keeps `AuditEvent` (mutable; new fields default to `None`, so
`test_chain_verify.py` still builds six-field events), `VerifyResult`, `compute_event_hash`, `genesis_hash` and
`verify_chain`, and adds `verify_rows`; all of them delegate to `audit_hash`. `main.py` maps rows with
`chain_event_from_row` (through `verify_rows`), so the mapping is unit-tested. The job imports `mintkey_models`, so it
runs where that package and its dependencies (SQLAlchemy, pydantic) are importable, e.g.
`PYTHONPATH=packages/python/mintkey-models python apps/audit-verify-job/main.py`. No `sys.path` change in production
code.

## Interfaces

In `mintkey_models.audit_hash` (all public, typed for `mypy --strict`):

```python
GENESIS_PREFIX: Final[str] = "mintkey-audit-genesis-v1:"
def genesis_hash(tenant_id: str) -> bytes
def canonical_at(at: datetime) -> str
def canonical_id(value: object) -> str | None
def canonical_event_fields(*, event_id: object, tenant_id: object, event_type: str, actor_id: object,
                           actor_type: str | None, target_id: object, target_type: str | None,
                           payload: Mapping[str, Any], at: datetime) -> dict[str, Any]
def canonical_json_bytes(fields: Mapping[str, Any]) -> bytes
def chain_hash(canonical: bytes, prev_hash: bytes) -> bytes
@dataclass(frozen=True) class ChainEvent   # the 13 columns, request_id and trace_id default None
def event_hash(event: ChainEvent) -> bytes
def chain_event_from_row(row: Any) -> ChainEvent
@dataclass(frozen=True) class ChainResult  # ok, chain_length, last_event_id, first_bad_event_id,
                                           # expected_hash, actual_hash, message
def verify_events(events: Sequence[ChainEvent]) -> ChainResult
```

In `apps/audit-verify-job/verify.py`: `AuditEvent`, `VerifyResult` (unchanged fields `ok`, `chain_length`,
`first_bad_event_id`, `message`), `genesis_hash` (re-exported), `compute_event_hash(event: AuditEvent, prev_hash:
bytes) -> bytes`, `verify_chain(events: List[AuditEvent]) -> VerifyResult`, `verify_rows(rows: Sequence[Any]) ->
VerifyResult`.

The SELECT of both verifiers is the literal `SELECT id, tenant_id, event_type, actor_id, actor_type, target_id,
target_type, payload, at, prev_hash, hash, request_id, trace_id FROM audit_events WHERE tenant_id = :tid ORDER BY at
ASC, id ASC` (`:tenant_id` in `audit_admin.py`, as today). It stays a string literal: the architecture test
`tests/acceptance/test_no_sql_injection.py` refuses anything else inside `text()` in admin-api.

## Failure cases

- An event changed in any column, a deleted event in the middle, a fork, a bad genesis link: not ok, naming the
  first event the walk could not verify.
- A deleted last event, or the last event changed together with its hash: not detectable from the rows alone (the
  head in `audit_chain_state` would show it); unchanged, out of scope.
- `at` without a time zone (`canonical_at`), a row without `id` or `tenant_id` (`chain_event_from_row`): `ValueError`;
  the job logs it and exits 1 as for any error; the endpoint answers 500 as for any unhandled error.
- `payload` as JSON text that does not parse: `json.JSONDecodeError` (a `ValueError`), as above.
- A tenant without an `audit_chain_state` row: `audit_emit` links its events to 32 zero bytes and does not move a
  head, so its chain does not verify. Both tenant-creation paths seed the row; unchanged.
- No events: ok, `chain_length` 0.

## Open questions

- Postgres normalises JSONB numbers: a float written in exponent form with an integral value (for example `1e20`)
  reads back as an integer and would not verify. Inferred from JSONB's numeric storage, not run here. The audit
  payloads seen in the code carry ids, names, counts and flags; if a payload ever needs such floats, the writer
  should hash the value Postgres returns (`SELECT CAST(:payload AS jsonb)`), a separate change.
- That stored rows round-trip `at` and the payload exactly is also shown by `tests/acceptance/test_audit_chain.py`
  (`test_hash_computation_matches_spec`, Docker, run by ci.yml's acceptance job, not by the L4 gate); its CI status
  was not checked here.
- `apps/audit-verify-job` has no deployment definition in this repository (no Dockerfile, compose service or chart
  job); who runs it and with which environment is not known.
