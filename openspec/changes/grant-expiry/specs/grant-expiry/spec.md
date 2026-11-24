# Grant expiry

## Purpose

A permission grant may carry an expiry and always records who gave it. A grant past its expiry is absent for the
agent, and a token never outlives the grant it was issued under. The write path is shared by every caller that
creates or removes a grant.

## ADDED Requirements

### Requirement: The schema stores a grant's expiry and grantor
The changelog `apps/admin-api/db/changelog/030-grant-expiry.yaml`, included once in `db.changelog-master.yaml`, SHALL add
to `permission_grants` the columns `expires_at` (TIMESTAMPTZ, nullable), `grantor_type` (TEXT, not null, default
`operator`, with a CHECK that allows `operator` and `agent`) and `grantor_id` (UUID, nullable), and an index on
`(tenant_id, grantor_id)`. The columns SHALL NOT be added to `mintkey_models/db.py`; they SHALL be added to the Core
table `permission_grants` of `admin_api/db/tables.py`.

#### Scenario: the changelog adds the columns
- **WHEN** the changelog file is parsed as YAML and the master changelog is read
- **THEN** the file holds an `addColumn` for each of the three columns with the types above, `expires_at` and
  `grantor_id` without `nullable: false`, `grantor_type` with default value `operator` and `nullable: false`, an SQL
  change whose text contains `CHECK (grantor_type IN ('operator', 'agent'))`, and a `createIndex`; exactly one include in
  the master names `030-grant-expiry.yaml`

#### Scenario: the Core table knows the columns
- **WHEN** `admin_api.db.tables.permission_grants.c` is read
- **THEN** it has the keys `expires_at`, `grantor_type` and `grantor_id`, and `mintkey_models/db.py` as text contains
  none of the three names inside the `PermissionGrant` class

### Requirement: The expiry rules and the cap have one implementation
`admin_api.services.grant_expiry` (typed for `mypy --strict`) SHALL give:

```python
AGENT_GRANT_MAX_TTL_DEFAULT_SECONDS: Final[int] = 604_800
AGENT_GRANT_MAX_TTL_CEILING_SECONDS: Final[int] = 7_776_000
GRANTOR_OPERATOR: Final[str] = "operator"
GRANTOR_AGENT: Final[str] = "agent"
def agent_grant_max_ttl_seconds() -> int
def is_expired(expires_at: datetime | None, now: datetime) -> bool
class GrantExpiryError(Exception):   # .reason: expires_at_timezone_required | expires_at_in_past |
    reason: str                      #          expires_at_required | expires_at_too_far
def check_grant_expiry(expires_at: datetime | None, grantor_type: str, now: datetime) -> None
```

`agent_grant_max_ttl_seconds()` SHALL read
`MINTKEY_AGENT_GRANT_MAX_TTL` as decimal seconds and return 604800 when it is unset, empty, not a decimal integer or
below 1, and 7776000 when it is larger than 7776000. `is_expired(expires_at, now)` SHALL be true exactly when
`expires_at` is not None and not after `now`. `check_grant_expiry(expires_at, grantor_type, now)` SHALL raise
`GrantExpiryError` with the reason `expires_at_timezone_required` for a datetime without an offset,
`expires_at_in_past` for a value not after `now`, `expires_at_required` for an agent grantor with None, and
`expires_at_too_far` for an agent grantor with a value after `now` plus the cap; otherwise it SHALL return None.

#### Scenario: the cap reader
- **WHEN** the variable is unset, `""`, `"abc"`, `"0"`, `"-5"`, `"3600"`, `"604800"` and `"99999999"`
- **THEN** `agent_grant_max_ttl_seconds()` returns 604800, 604800, 604800, 604800, 604800, 3600, 604800 and 7776000

#### Scenario: operator and agent rules
- **WHEN** `check_grant_expiry` runs with a fixed `now` for an operator with None, an operator one hour ahead, an
  operator one second ago, an agent with None, an agent one day ahead, an agent exactly at the cap, an agent one
  second past the cap, and a naive datetime
- **THEN** the results are no error, no error, `expires_at_in_past`, `expires_at_required`, no error, no error,
  `expires_at_too_far`, and `expires_at_timezone_required`

#### Scenario: the expiry boundary
- **WHEN** `is_expired` runs with `expires_at` equal to `now`, one second before `now`, one second after `now`, and None
- **THEN** it returns true, true, false and false

### Requirement: One write path creates and removes grants
`admin_api.services.grants` SHALL give:

```python
@dataclass(frozen=True)
class Grantor:
    type: str                      # "operator" | "agent"
    id: str | None                 # DB uuid text of the operator or the agent
@dataclass(frozen=True)
class GrantRecord:
    id: str; wire_id: str; agent_id: str; service_id: str; action: str   # ids as DB uuid text; wire_id is perm_...
    constraints: dict[str, Any]; expires_at: datetime | None
    grantor_type: str; grantor_id: str | None; created_at: datetime | None
    created: bool                  # False: an identical live grant already existed
class GrantConflict(Exception): ...
async def write_grant(session: AsyncSession, *, tenant_id: UUID, agent_id: str, service_id: str, action: str,
                      constraints: dict[str, Any], expires_at: datetime | None, grantor: Grantor,
                      now: datetime | None = None) -> GrantRecord
async def delete_grant(session: AsyncSession, *, tenant_id: UUID, grant_id: str,
                       agent_id: str | None = None) -> GrantRecord | None
def grant_granted_audit_payload(record: GrantRecord) -> dict[str, Any]
def grant_revoked_audit_payload(record: GrantRecord, revoked_by: Grantor) -> dict[str, Any]
def grant_revoked_notify_payload(tenant_id: UUID, record: GrantRecord, revoked_at: datetime) -> dict[str, Any]
def grant_wire_fields(record_or_row: Any, now: datetime) -> dict[str, Any]
```

`write_grant` SHALL run `check_grant_expiry` before any statement (the caller has set the tenant context and checked
that the agent and the service exist). Its first statement SHALL be the transaction-level advisory lock `SELECT
pg_advisory_xact_lock(hashtextextended(:key, 0))` with `key` equal to `grant:<tenant_id>:<agent_id>:<service_id>:<action>`
(ids as DB uuid text), so concurrent writers of one (agent, service, action) run one after the other until their
transactions end and the second sees the first's row; no unique constraint is added, because rows written before this
change may repeat a key and a "live rows only" constraint cannot name `now()`. It SHALL select the row of (tenant, agent,
service, action) with `ORDER BY (expires_at IS NULL) DESC, expires_at DESC, created_at DESC, id LIMIT 1` (the ordering of
`request_token`, so a live row comes first when one exists): a live row with equal
constraints and expiry is returned with `created` false; a live row with other constraints or another expiry raises
`GrantConflict`; an expired row (`is_expired`) is deleted; then it SHALL insert the grant with `grantor_type`, `grantor_id`,
`expires_at` and `created_by` (the grantor id, or the agent id without one), upsert the budget counter when the constraints
have a budget, and return the new record. For an existing row each of `expires_at`, `grantor_type`, `grantor_id` and
`created_at` is read with the rule that a value of the wrong type reads as its default (`expires_at` None, `grantor_type` `operator`, `grantor_id` None, `created_at` None). `delete_grant` SHALL select the matching row (and agent, when given),
delete it and return its record, or return None and delete nothing. The payload builders SHALL give: granted `{perm_id,
agent_id, service_id, action, constraints, expires_at (ISO or null), grantor_type, grantor_id}`; revoked `{permission_id,
agent_id, service_id, action, grantor_type, grantor_id, revoked_by_type, revoked_by_id}`; NOTIFY `{event:
"agent.permission.revoked", tenant_id, agent_id, permission_id, service_id, revoked_at}`; ids in wire form (`agent_`, `svc_`,
`perm_`), a value that is not a UUID text passing through, `tenant_id` the UUID text. In the NOTIFY payload `revoked_at` SHALL
be a string: the ISO-8601 timestamp in UTC with an offset, `revoked_at.astimezone(timezone.utc).isoformat()` (a naive
datetime reads as UTC), for example `2026-11-25T10:00:00+00:00`, with `+00:00` and never `Z`, and with `.123456` before the
offset when the datetime has microseconds. The proxy's revocation change parses it. `grant_wire_fields` SHALL give `{"expires_at": ISO or null,
"expired": bool, "grantor_type": str, "grantor_id": str or null}`: the `agent_...` wire id for an agent grantor, the
operator's UUID text otherwise, `operator` for a missing type.

#### Scenario: an operator and an agent write grants
- **WHEN** `write_grant` runs with `Grantor("operator", <id>)` and no expiry, and with `Grantor("agent", <id>)` and an
  expiry one day ahead (one call with a budget constraint)
- **THEN** each returns `created` true; the INSERT parameters hold the grantor type and id, the expiry (null for the
  first) and `created_by` equal to the grantor id; the budget call also runs a `budget_counters` statement

#### Scenario: an identical grant is returned, another is refused, an expired one is replaced
- **WHEN** the existing row has the same constraints and expiry; then another expiry; then other constraints; and, in a
  fourth call, a stored expiry in the past against a request for a future one
- **THEN** the first returns the existing id with `created` false, the next two raise `GrantConflict` and run no INSERT,
  and the fourth runs one DELETE of the expired row and one INSERT and returns `created` true; a `MagicMock` row as the
  existing grant reads as `operator`, no grantor id and no expiry

#### Scenario: two concurrent writes of one grant
- **WHEN** two sessions of an in-memory fake, which shares one grant table and implements `pg_advisory_xact_lock` as a lock
  held until that session's `commit()`, run `write_grant` at the same time through `asyncio.gather` with the same agent,
  service, action, constraints and expiry; and again with two different expiries
- **THEN** the first run stores exactly one row, one result has `created` true and the other `created` false; the second
  run stores exactly one row, one call returns and the other raises `GrantConflict`; in both runs the first statement of
  each session is the lock statement with the `key` of the requirement

#### Scenario: a rule violation writes nothing
- **WHEN** `write_grant` runs for an agent grantor with no expiry, a past expiry and an expiry beyond the cap
- **THEN** each raises `GrantExpiryError` and the fake session saw no statement

#### Scenario: delete returns the record or nothing
- **WHEN** `delete_grant` runs for a stored grant and for an id with no row
- **THEN** the first returns the stored agent, service, action and grantor after one DELETE, the second returns None
  and runs no DELETE

#### Scenario: the payload builders
- **WHEN** the builders run on a record with an agent grantor and a past expiry
- **THEN** their payloads have exactly the keys above, and `grant_wire_fields` shows `expired` true

#### Scenario: the NOTIFY payload pins the revoked_at format
- **WHEN** `grant_revoked_notify_payload` runs with `revoked_at` equal to `datetime(2026, 11, 25, 12, 0, tzinfo=timezone(timedelta(hours=2)))`,
  to `datetime(2026, 11, 25, 10, 0, 0, 123456, tzinfo=timezone.utc)` and to the naive `datetime(2026, 11, 25, 10, 0, 0)`
- **THEN** `revoked_at` is the string `2026-11-25T10:00:00+00:00`, then `2026-11-25T10:00:00.123456+00:00`, then
  `2026-11-25T10:00:00+00:00`, `tenant_id` is the tenant's UUID text, and each payload passes `json.dumps`

### Requirement: The operator API takes an expiry and records the grantor
`POST /v1/tenants/{tenant_id}/agents/{agent_id}/permissions` SHALL accept `expires_at` and SHALL call `write_grant`
with `Grantor("operator", <operator id of get_session_context>)`; a `granted_by` in the body SHALL NOT influence
the grantor or `created_by`. It SHALL answer, as flat JSON bodies like the route's existing `invalid_id` answer (the keys are at the top level, not under
`detail`), 422 `{"mintkey:code": "invalid_expires_at", "title": "Invalid expires_at", "reason": "<the GrantExpiryError reason>"}`
for a `GrantExpiryError`, and 409 `{"mintkey:code": "permission_constraints_conflict", "title": "A permission grant with
different constraints already exists"}` (the existing body) for a `GrantConflict`; an `expires_at` that is not a datetime
is refused by request validation, unchanged. It SHALL keep its 201 and idempotent 200 answers. Every grant object of
the operator API SHALL carry `expires_at`, `expired`, `grantor_type` and `grantor_id`. `DELETE .../permissions/{id}` SHALL
call `delete_grant`, and for a deleted grant emit `agent.permission.revoked` with the revoked payload (actor the
operator) and publish the revoked NOTIFY payload on `mintkey:agent`, and for no row answer 204 and emit nothing.
`GET /v1/tenants/{tenant_id}/permissions` SHALL accept `grantor_agent_id`, an `agent_` wire id or a UUID, and return only the
grants with `grantor_type = 'agent'` and `grantor_id` equal to that agent's UUID (422 `{"mintkey:code": "invalid_id", "title":
"Invalid agent_id"}` for a value that does not decode).

#### Scenario: a grant with an expiry
- **WHEN** an operator posts a grant with `expires_at` one day ahead and `"granted_by": "agent_other"`
- **THEN** the answer is 201 with that `expires_at`, `expired` false, `grantor_type` `operator` and `grantor_id` the
  operator's id from the session context; the INSERT's `created_by` is that id, not `agent_other`; and the audit
  payload carries the expiry and the grantor

#### Scenario: invalid and conflicting requests
- **WHEN** the body has `expires_at` one hour ago, `"2030-01-01T00:00:00"` (no offset), and a future expiry for an agent,
  service and action that already have a live grant with another expiry
- **THEN** the answers are the JSON bodies `{"mintkey:code": "invalid_expires_at", "title": "Invalid expires_at", "reason":
  "expires_at_in_past"}`, the same with `"expires_at_timezone_required"`, and `{"mintkey:code":
  "permission_constraints_conflict", "title": "A permission grant with different constraints already exists"}` with status
  422, 422 and 409; no INSERT ran

#### Scenario: the lists show the new fields
- **WHEN** the agent list and the tenant list run over a grant with a past expiry, one with none and one given by an
  agent, and the tenant list runs with `?grantor_agent_id=<agent wire id>` and with `?grantor_agent_id=x`
- **THEN** the objects show `expired` true; `expired` false with `expires_at` null; `grantor_type` `agent` with the
  agent's wire id; the filter returns only the agent's grant (its SELECT text contains `grantor_type = 'agent'` and `grantor_id`, with the
  agent's UUID bound) and `x` answers 422 with `"mintkey:code": "invalid_id"`; the SELECT texts contain `expires_at`,
  `grantor_type` and `grantor_id`

#### Scenario: revoke names what it revoked
- **WHEN** an operator revokes a stored grant, and then an id with no row
- **THEN** the first answers 204 and emits one `agent.permission.revoked` with `service_id`, `action` and the grantor, and
  one NOTIFY on `mintkey:agent` whose payload has `service_id` and a `revoked_at` string that ends with `+00:00`; the second answers 204 and emits no
  audit event and no NOTIFY

### Requirement: An expired grant is absent for the agent
`request_token` SHALL select the grant of (agent, service, action) with its `expires_at` and with `ORDER BY (expires_at IS NULL)
DESC, expires_at DESC, created_at DESC, id LIMIT 1`, so that when several rows exist (written before this change) the one
that lasts longest decides, a grant without an expiry beating any with one, and ties go to the newest row; and when it is not None and `grant_ttl_seconds` returns
None SHALL answer 403 `mintkey:not_authorized` with `reason_code` `grant_expired` and a `hint`, write `token.denied` with
that reason, and call neither the rate limiter, the time-window check nor the broker. `mintkey_list_services`,
`mintkey_discover` and `mintkey_describe_service` SHALL select only grants for which `(expires_at IS NULL OR expires_at >
now())`; the classical key creation (`api_keys.py`) and every grant count and access filter of `agents.py` SHALL do the same.

#### Scenario: an expired grant is denied
- **WHEN** an agent requests a token for a service whose grant has `expires_at` ten seconds ago, and again for one with
  2 seconds left
- **THEN** both answer 403 with `reason_code` `grant_expired`, a `token.denied` event with that reason is written for
  each, and the broker is not called

#### Scenario: the grant select is ordered
- **WHEN** `request_token` runs on a recording fake session
- **THEN** the statement that reads `permission_grants` contains `ORDER BY (expires_at IS NULL) DESC, expires_at DESC,
  created_at DESC, id` and `LIMIT 1`, and it selects `expires_at`

#### Scenario: a grant without an expiry behaves as before
- **WHEN** the grant row has no `expires_at` attribute, a null one, or a non-datetime value
- **THEN** the token is issued and the broker payload has `ttl_seconds` 600

#### Scenario: discovery hides what the database says is expired
- **WHEN** `list_services`, `discover` and `describe_service` run on a fake session
- **THEN** each executed statement that reads `permission_grants` contains `expires_at IS NULL OR` and `expires_at >
  now()` for the grants alias it uses

#### Scenario: the other readers ignore an expired grant
- **WHEN** a classical key is created, and `list_agents` and `get_agent` run
- **THEN** every executed statement that reads `permission_grants` contains `expires_at > now()`

### Requirement: A token never outlives its grant
`mcp_server.policy.grant_expiry` SHALL give `MAX_TOKEN_TTL_SECONDS = 600`, `MIN_TOKEN_TTL_SECONDS = 5` and `def
grant_ttl_seconds(expires_at: object, now: datetime) -> int | None` (a naive datetime reads as UTC), which SHALL return 600 for None or a non-datetime, and
for a datetime `floor(seconds until expires_at)` capped at 600, and None when that is below 5. `request_token` SHALL
send that value as `ttl_seconds` to the broker.

#### Scenario: the lifetime function
- **WHEN** it runs with a fixed `now` and an expiry of None, 3600 s, 600 s, 100.9 s, 5 s, 4.9 s, 0 s and -1 s ahead
- **THEN** it returns 600, 600, 600, 100, 5, None, None and None

#### Scenario: the broker receives the shortened lifetime
- **WHEN** an agent requests a token for a grant that expires in about 120 s
- **THEN** the broker payload's `ttl_seconds` is an integer from 100 to 120 inclusive and the answer is 200

### Requirement: The audit contract records the grantor and the expiry
`docs/architecture/contracts/events/audit-event.schema.json` SHALL add to the payload of `ev_agent_permission_granted`
the optional properties `expires_at`, `grantor_type` and `grantor_id`, to `ev_agent_permission_revoked` the optional
properties `grantor_type`, `grantor_id`, `revoked_by_type` and `revoked_by_id`, and `grant_expired` to the
`reason_code` enum of `ev_token_denied`.

#### Scenario: the contract names them
- **WHEN** the schema file is loaded as JSON
- **THEN** the three definitions list those properties and that enum value, and the `required` lists they had are
  unchanged
