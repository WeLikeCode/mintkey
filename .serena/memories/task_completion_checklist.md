# Task Completion Checklist

When completing any implementation task in Mintkey, verify ALL of the following that apply:

## Always
- [ ] SQL uses bound parameters only (no f-string interpolation in `text()` calls)
- [ ] `::type` casts replaced with `CAST(:param AS type)` (asyncpg incompatibility)
- [ ] `set_tenant_context(session, tenant_id)` called before any tenant-scoped query
- [ ] No plaintext credentials in logs, audit payloads, or HTTP responses
- [ ] `audit_emit()` called for every state change
- [ ] `notify_change()` called on the global channel after state changes

## If schema changed
- [ ] Liquibase changelog added in `admin-api/db/changelog/`
- [ ] New changelog included in `db.changelog-master.yaml`
- [ ] RLS policy created in same changeset as new table
- [ ] `GRANT SELECT,INSERT,UPDATE,DELETE ON <table> TO mintkey_app;` added
- [ ] RLS architecture test passes: `pytest tests/architecture/test_rls_coverage.py -v`
- [ ] SQLAlchemy mirror diff clean (if using sqlacodegen)

## If new API endpoint added
- [ ] Route registered in `admin_api/main.py`
- [ ] CSRF exempt if uses Bearer auth (decorate with `@no_csrf`)
- [ ] OpenAPI parity check: FastAPI-emitted spec matches `docs/architecture/contracts/rest/openapi.yaml`
- [ ] Audit chokepoint test passes: `pytest tests/architecture/test_audit_coverage.py -v`

## If credential code path touched
- [ ] Plaintext canary grep returns empty: `docker compose logs | grep -E "canary-demo-api-key"`
- [ ] No plaintext in OTel span attributes

## Testing commands
```bash
pytest tests/unit/admin_api/ -v
pytest tests/architecture/ -v
go test ./services/... (from repo root)
python3 scripts/e2e_smoke.py --no-twilio
```

## Key anti-patterns (never do)
- Add a column in SQLAlchemy (Liquibase only — ADR-0015)
- Edit an Accepted ADR (write a new superseding ADR)
- Cache plaintext credentials beyond request scope (ADR-0014.4)
- Use per-tenant pg_notify channel names (channels are global — ADR-0014.1)
- Use UUIDs as wire IDs (ULIDs with prefix only — ADR-0017.11)
- Use `default` as tenant slug (use `t_default` — ADR-0017.9)
- Commit with `--no-verify`
