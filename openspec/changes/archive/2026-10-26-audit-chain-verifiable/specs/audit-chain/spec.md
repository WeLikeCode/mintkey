# Audit hash chain

## Purpose

How an audit event's hash is formed from the values stored in `audit_events`, and how the verify job and the
verify-chain endpoint check a tenant's chain with that same form, so that an intact chain verifies and a change to
any stored field of any event is reported.

## ADDED Requirements

### Requirement: One canonical form for the audit event hash
The module `mintkey_models.audit_hash` (`packages/python/mintkey-models/mintkey_models/audit_hash.py`, standard
library only) SHALL define the canonical form, and the writer and every verifier SHALL use it:
- `GENESIS_PREFIX = "mintkey-audit-genesis-v1:"` and `genesis_hash(tenant_id: str) -> bytes`:
  `sha256((GENESIS_PREFIX + tenant_id).encode("utf-8")).digest()`.
- `canonical_at(at: datetime) -> str`: `at.astimezone(timezone.utc).isoformat()`; a naive `at` (no `tzinfo`) SHALL
  raise `ValueError`.
- `canonical_id(value: object) -> str | None`: `None` for `None`; else `str(UUID(str(value)))` when `str(value)` parses
  as a UUID, else `str(value)`.
- `canonical_event_fields(*, event_id, tenant_id, event_type, actor_id, actor_type, target_id, target_type, payload,
  at) -> dict[str, Any]`: the keys `id`, `tenant_id`, `actor_id`, `target_id` (through `canonical_id`), `event_type`,
  `actor_type`, `target_type` (as given), `payload` (`dict(payload)`) and `at` (`canonical_at(at)`).
- `canonical_json_bytes(fields: Mapping[str, Any]) -> bytes`: `json.dumps` of `fields` without the key `hash`, with
  `sort_keys=True` and `separators=(",", ":")`, encoded as UTF-8.
- `chain_hash(canonical: bytes, prev_hash: bytes) -> bytes`: `sha256(canonical + prev_hash).digest()`.

This form SHALL be byte for byte the one `audit_emit` has always hashed, so events already stored verify without a
migration. `mintkey_models.audit.compute_hash(event_dict, prev_hash)` SHALL keep its result and SHALL equal
`chain_hash(canonical_json_bytes(event_dict), prev_hash)`.

#### Scenario: the canonical bytes of a fixed event
- **WHEN** `canonical_event_fields` is given `event_id="0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10"`,
  `tenant_id="5f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5"`, `event_type="service.created"`,
  `actor_id="7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f"`, `actor_type="operator"`,
  `target_id="c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6"`, `target_type="service"`, `payload={"name": "svc-a", "count": 2}`
  and `at=datetime(2026, 10, 25, 9, 30, 0, 123456, tzinfo=timezone.utc)`, and its result goes to
  `canonical_json_bytes`
- **THEN** the bytes are
  `{"actor_id":"7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f","actor_type":"operator","at":"2026-10-25T09:30:00.123456+00:00","event_type":"service.created","id":"0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10","payload":{"count":2,"name":"svc-a"},"target_id":"c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6","target_type":"service","tenant_id":"5f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5"}`,
  `genesis_hash` of the tenant is hex `58d21bc79de12e830899d1008e35c0fe27d883946121948b6cb5ee78820d8a89`, and
  `chain_hash(<those bytes>, <that genesis>)` is hex
  `d653e8c4e55acddea203e75f389c0f5d4b631d4d78426fa6a6d013c669e22372`

#### Scenario: the writer's hash function keeps its result
- **WHEN** `mintkey_models.audit.compute_hash` is given the dict of the scenario above with `at` as the string
  `"2026-10-25T09:30:00.123456+00:00"` and the genesis hash of that tenant
- **THEN** it returns the digest `d653e8c4e55acddea203e75f389c0f5d4b631d4d78426fa6a6d013c669e22372`

#### Scenario: the forms of a time
- **WHEN** `canonical_at` is given `datetime(2026, 10, 25, 9, 30, 0, 123456, tzinfo=timezone.utc)`,
  `datetime(2026, 10, 25, 9, 30, tzinfo=timezone.utc)`,
  `datetime(2026, 10, 25, 12, 30, tzinfo=timezone(timedelta(hours=3)))` and the naive `datetime(2026, 10, 25, 9, 30)`
- **THEN** it returns `"2026-10-25T09:30:00.123456+00:00"`, `"2026-10-25T09:30:00+00:00"` and
  `"2026-10-25T09:30:00+00:00"`, and raises `ValueError` for the naive one

#### Scenario: the forms of an id
- **WHEN** `canonical_id` is given `UUID("0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10")`,
  `"0B0E7C51-3A52-4C5E-9D5B-2F4F6F3F9A10"`, `"tenant_ABC"` and `None`
- **THEN** it returns `"0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10"` twice, then `"tenant_ABC"` and `None`

### Requirement: The chain is verified from the stored columns by its links
`mintkey_models.audit_hash` SHALL define:
- `ChainEvent`, a frozen dataclass of the 13 stored columns: `id: str`, `tenant_id: str`, `event_type: str`,
  `actor_id: str | None`, `actor_type: str | None`, `target_id: str | None`, `target_type: str | None`,
  `payload: Mapping[str, Any]`, `at: datetime`, `prev_hash: bytes`, `hash: bytes`, `request_id: str | None = None`,
  `trace_id: str | None = None`.
- `event_hash(event: ChainEvent) -> bytes`: `chain_hash(canonical_json_bytes(canonical_event_fields(...)),
  event.prev_hash)` over the event's nine hashed fields.
- `chain_event_from_row(row: Any) -> ChainEvent`: reads those 13 attributes of a database row; ids through
  `canonical_id`; `payload` a mapping as is, a `str` through `json.loads`, `None` as `{}`; `prev_hash` and `hash`
  through `bytes()`; a row whose `id` or `tenant_id` is `None` SHALL raise `ValueError`.
- `ChainResult`, a frozen dataclass: `ok: bool`, `chain_length: int`, `last_event_id: str | None`,
  `first_bad_event_id: str | None`, `expected_hash: bytes | None`, `actual_hash: bytes | None`, `message: str`.
- `verify_events(events: Sequence[ChainEvent]) -> ChainResult`, which SHALL NOT depend on the order of `events`.
  Starting at `genesis_hash(events[0].tenant_id)`, it walks to the event whose `prev_hash` is the current hash (the
  first such event in list order), at most `len(events)` steps. At each event: when `event_hash(event) !=
  event.hash`, the result is not ok with `expected_hash` the computed hash, `actual_hash` the stored hash and
  `message` `"hash mismatch at event <id>"`; when `request_id` or `trace_id` is not `None` (the hash does not cover
  them and the writer never sets them), not ok with both hashes `None` and `message` `"event <id> has request_id or
  trace_id set"`; else the current hash becomes `event.hash`. When the walk stops before every event was visited, the
  result is not ok for the first event in list order not visited, with `expected_hash` the current hash,
  `actual_hash` that event's `prev_hash` and `message` `"event <id> does not follow the chain"`. A not-ok result
  names its event in `first_bad_event_id`. `chain_length` is the number of events verified before the result and
  `last_event_id` the last of them (`None` when there is none). An intact chain is ok with `message`
  `"chain intact"`; no events is ok, `chain_length` 0, `message` `"empty chain"`.

#### Scenario: an event written by audit_emit verifies from its stored row
- **WHEN** `audit_emit` writes one event through a fake session and the row is rebuilt as Postgres returns it (UUID
  ids, the `payload` JSON text parsed, the bound `at` datetime, `request_id` and `trace_id` `None`)
- **THEN** `verify_events([chain_event_from_row(row)])` is ok with `chain_length` 1 and `last_event_id` the event's id

#### Scenario: a chain of three verifies in any order
- **WHEN** `audit_emit` writes three events for one tenant and their rows are given in reverse order
- **THEN** the result is ok with `chain_length` 3 and `last_event_id` the id of the third event written

#### Scenario: a time read back in another zone verifies
- **WHEN** the stored row's `at` is converted with `astimezone(timezone(timedelta(hours=3)))` before the check
- **THEN** the result is ok

#### Scenario: a payload read back as JSON text verifies
- **WHEN** the stored row's `payload` is the JSON text bound in the INSERT instead of a dict
- **THEN** the result is ok

#### Scenario: an event that does not follow the chain
- **WHEN** only the second of two events written by `audit_emit` is checked
- **THEN** the result is not ok, `first_bad_event_id` is its id, `expected_hash` is the tenant's genesis hash,
  `actual_hash` is its `prev_hash`, `chain_length` is 0 and `last_event_id` is `None`

#### Scenario: two events that follow the same hash
- **WHEN** the rows are the first event, the second event, and a copy of the second event with another `id` and its
  `hash` recomputed
- **THEN** the result is not ok and `first_bad_event_id` is the copy's id

#### Scenario: no events
- **WHEN** `verify_events([])` is called
- **THEN** it is ok with `chain_length` 0, `last_event_id` `None` and `message` `"empty chain"`

### Requirement: Altering any stored field of an event fails its verification
For an event written by `audit_emit`, changing any one of its 13 stored columns SHALL make `verify_events` return a
result that is not ok.

#### Scenario: each stored field altered in turn
- **WHEN** one column of the stored row is changed before the check: `id`, `tenant_id`, `actor_id`, `target_id` or
  `request_id` to a new UUID, `event_type` to `"other.type"`, `actor_type` to `"agent"`, `target_type` to `"service"`,
  `payload` to `{"name": "svc-b", "count": 2}`, `at` by one microsecond, `prev_hash` to 32 bytes `0x01`, `hash` to 32
  bytes `0x02`, `trace_id` to `"trace-1"`
- **THEN** each result is not ok, and `first_bad_event_id` is the row's id (the new id when `id` was changed)

#### Scenario: a payload change reports both hashes
- **WHEN** the stored payload is changed to `{"name": "svc-b", "count": 2}`
- **THEN** `expected_hash` is `event_hash` of the changed event and `actual_hash` is the stored hash

### Requirement: The verify job checks a chain with the canonical form
`apps/audit-verify-job/verify.py` SHALL import the canonical form from `mintkey_models.audit_hash` and keep its public
names. `AuditEvent` SHALL keep its six fields and gain `actor_id`, `actor_type`, `target_id`, `target_type`, `at`,
`request_id` and `trace_id`, each defaulting to `None`. `compute_event_hash(event: AuditEvent, prev_hash: bytes) ->
bytes` SHALL be the canonical hash of the event's fields with `prev_hash`, and SHALL raise `ValueError` when
`event.at` is `None`. `verify_chain(events: List[AuditEvent]) -> VerifyResult` and the new `verify_rows(rows:
Sequence[Any]) -> VerifyResult` SHALL return `verify_events`' `ok`, `chain_length`, `first_bad_event_id` and
`message`. `main.py` SHALL select the 13 columns ordered by `at, id` and check them with `verify_rows`.

#### Scenario: the job verifies an event written by audit_emit
- **WHEN** `verify_rows` is given the stored row of an event written by `audit_emit`
- **THEN** it returns a `VerifyResult` that is ok with `chain_length` 1

#### Scenario: the job reports an altered field
- **WHEN** the stored row's `payload`, `at`, `actor_id` or `request_id` is changed as in the requirement above
- **THEN** `verify_rows` is not ok and `first_bad_event_id` is the row's id

#### Scenario: a dataclass chain verifies, and an event without a time is refused
- **WHEN** `verify_chain` is given `AuditEvent`s built with every field from the stored rows of two events written by
  `audit_emit`, and `compute_event_hash` is given an `AuditEvent` whose `at` is `None`
- **THEN** `verify_chain` is ok with `chain_length` 2, and `compute_event_hash` raises `ValueError`

#### Scenario: main.py reads the 13 columns and exits by the result
- **WHEN** `main._run(None)` runs with `DATABASE_URL` set and `sqlalchemy.ext.asyncio.create_async_engine` replaced
  by a fake whose connection answers the tenants query with one tenant and the events query with the stored row of an
  event written by `audit_emit`, then again with that row's payload changed
- **THEN** the events statement, with each run of whitespace made one space, is `SELECT id, tenant_id, event_type,
  actor_id, actor_type, target_id, target_type, payload, at, prev_hash, hash, request_id, trace_id FROM audit_events
  WHERE tenant_id = :tid ORDER BY at ASC, id ASC`, and `_run` returns 0, then 1

### Requirement: The verify-chain endpoint checks a chain with the canonical form
`POST /v1/admin/audit/verify-chain` (`admin_api.api.audit_admin.verify_chain_endpoint`) SHALL select the 13 columns
of the tenant's events ordered by `at, id`, check them with `verify_events(chain_event_from_row(row) ...)`, and answer
as today: ok → `{"ok": true, "chain_length", "last_event_id", "verified_at"}`; not ok → `{"ok": false,
"first_bad_event_id", "expected_hash", "actual_hash"}`, the hashes as lowercase hex or `null`, every id a string.

#### Scenario: the endpoint verifies an event written by audit_emit
- **WHEN** the session returns the stored row of an event written by `audit_emit`
- **THEN** the answer is 200 with `ok` true, `chain_length` 1 and `last_event_id` the event's id as a string, and the
  statement that read the events, with each run of whitespace made one space, is `SELECT id, tenant_id, event_type,
  actor_id, actor_type, target_id, target_type, payload, at, prev_hash, hash, request_id, trace_id FROM audit_events
  WHERE tenant_id = :tenant_id ORDER BY at ASC, id ASC`

#### Scenario: the endpoint reports an altered payload
- **WHEN** the stored row's payload was changed
- **THEN** the answer is 200 with `ok` false, `first_bad_event_id` the event's id, `expected_hash` the hex of the
  recomputed hash and `actual_hash` the hex of the stored hash

#### Scenario: the endpoint reports an event that does not follow the chain
- **WHEN** the session returns only the second of two events written by `audit_emit`
- **THEN** `ok` is false, `expected_hash` is the hex of the tenant's genesis hash and `actual_hash` the hex of that
  event's `prev_hash`
