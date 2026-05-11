# Code Style and Conventions

## Python
- Type hints everywhere; mypy --strict compliance required
- Pydantic v2 models for request/response; `extra="forbid"` on all request models
- `from __future__ import annotations` at top of every file
- Async-first: all FastAPI endpoints and DB operations are async
- SQLAlchemy `text()` with bound parameters only — never f-strings in SQL (ADR-0008)
- `::type` PostgreSQL casts NOT used in asyncpg — use `CAST(:param AS type)` instead
- structlog for logging; never log plaintext credentials
- No comments unless WHY is non-obvious
- Module-level docstring describing the module's purpose, endpoints, and architecture refs

## Go
- Standard Go idioms; slog for structured logging
- No credentials in log output
- Distroless final images; multi-stage Dockerfiles
- Error wrapping with `fmt.Errorf("context: %w", err)`

## Naming
- Python files: snake_case; classes: PascalCase
- ULID wire IDs always have prefix (tenant_, agent_, svc_, cred_, perm_, svckey_, etc.)
- Internal DB UUIDs differ from wire ULIDs — DB stores UUID, wire returns ULID prefix + hex

## SQL patterns
```python
# Always use bound parameters:
await session.execute(
    text("SELECT * FROM agents WHERE id = :aid AND tenant_id = :tid"),
    {"aid": agent_id, "tid": str(tenant_id)},
)

# Always set tenant context before any query:
await set_tenant_context(session, tenant_id)

# asyncpg casts: use CAST not ::
CAST(:param AS jsonb)   # not :param::jsonb
CAST(:param AS text[])  # not :param::text[]
CAST(:param AS uuid)    # not :param::uuid
```

## Audit pattern
Every state-changing endpoint must call `audit_emit()`:
```python
from mintkey_models.audit import audit_emit
await audit_emit(
    session=session,
    tenant_id=tenant_id,
    event_type="resource.action",
    actor_id=None,
    actor_type="operator",
    target_id=internal_uuid,
    target_type="resource",
    payload={...},  # NO plaintext credentials in payload
)
```

## NOTIFY pattern
State changes also call `notify_change()` for the global channel:
```python
from admin_api.changes.publisher import notify_change
await notify_change(session, "mintkey:agent", {"event": "...", "tenant_id": ...})
```

## Liquibase discipline
- Schema changes: new `.yaml` file in `admin-api/db/changelog/`
- Include it in `db.changelog-master.yaml`
- Every table needs RLS changeset in same file as table creation
- SQLAlchemy models are mirrors only — generated from DB, not authoritative
