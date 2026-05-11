# PROGRESS.md — Mintkey implementation drive

> Companion to `team/remediation/MEGA_PROMPT.md`.
> Updated: 2026-05-11. Next agent: re-run §9 suite first, then continue from **§ Exact next step**.

---

## §1 Definition-of-Done checklist

| # | Item | Status | Last verified by |
|---|------|--------|-----------------|
| 1 | Stack boots — all 15 healthy + 2 one-shot jobs exit 0 | 🟡 PARTIAL | `docker ps --filter "name=mintkey" --format "{{.Names}}: {{.Status}}"` — 15 containers healthy; `liquibase` + `seed-job` Exited(0). **BUT** `mcp-server` and `mock-backend` containers are still running `nginx:alpine` placeholders (new Python images were built this session with `docker compose build mcp-server mock-backend` but containers not restarted). Seed-job steps 6–12 (AdminJS keypair, service identities, Broker keypair, Keycloak realm, bootstrap_completed audit) not independently verified. |
| 2 | Architecture tests pass | ✅ GREEN | `pytest tests/architecture/ -q` → **17 passed**, 0 failed, 0 skipped (2026-05-11, this session) |
| 3 | Every admin-API endpoint integration-tested (100% ENDPOINT_COVERAGE.md + testcontainer suite) | 🔴 RED | `ls tests/integration/admin_api/` → MISSING; `ls tests/acceptance/ENDPOINT_COVERAGE.md` → MISSING. Smoke script `scripts/e2e_smoke.py` covers 34/35 routes but is not an integration test suite (no testcontainers, no schema validation). |
| 4 | All unit/integration suites pass | 🟡 PARTIAL | `pytest tests/unit/ -q` → **142 passed** ✓; `pytest tests/acceptance/ -q` → **106 passed, 23 skipped** ✓; Go: all `go test ./...` green ✓ (all 4 services); **admin-ui: 7 failed / 40 passed ❌** (`RestResource` `.key` getter returns object instead of string — see § Admin-UI test failures); mcp-server own `pytest` finds 0 tests (tests live in `tests/unit/mcp_server/` which passes: 25 ✓) |
| 5 | Contract parity gates pass (OpenAPI parity, SQLAlchemy mirror, JSON schemas, protoc, Mermaid) | 🔴 UNKNOWN | Not run this session. Requires live migrated DB for SQLAlchemy diff. `openapi-spec-validator` not run. |
| 6 | Admin UI boots, login works, all resource lists render with data | 🔴 UNKNOWN | `admin-ui` container status: `Up 2 hours (healthy)`. But login not tested programmatically. 7 unit tests failing. mcp-server/mock-backend on nginx. |
| 7 | E2E-01 demo passes ≤ 90 s | 🔴 RED | `scripts/e2e_smoke.py` expanded to 34/35 endpoints but not run against live stack. mcp-server + mock-backend still on nginx:alpine. Broker/Kong/MCP flows untested end-to-end. |
| 8 | Multi-tenant + revocation/rotation/classical-key scenarios pass | 🟡 PARTIAL | `pytest tests/acceptance/test_tenant_isolation.py -q` → **11 passed** ✓ (architecture + runtime checks). Live revocation propagation (≤ 5 s) and credential rotation (≤ 30 s) not tested against running stack. |
| 9 | Clean diff — only required changes, no `--no-verify`, no ADR edits | 🟡 PARTIAL | No `--no-verify` used. Uncommitted working-tree changes present (see § Uncommitted state). No `docs/architecture/**` edits to make gates pass. |

---

## Current phase

**Phase 0 (Test Harness) — INCOMPLETE → Phase 1 (Foundation) — PARTIALLY DONE**

Phase 0 exit criteria not met: `tests/integration/admin_api/` and `ENDPOINT_COVERAGE.md` do not exist.

Phase 1 known-incomplete items:
- Seed-job steps 6–12 (AdminJS Ed25519 keypair → bootstrap-secrets/admin_ui_private.pem; 4 service_identities; Broker Ed25519 signing keypair; Keycloak realm import; `tenant.bootstrap_completed` audit; `--rotate-bootstrap`)
- `mintkey_app_ro` read-only role + RLS scope for AdminJS reads (OQ — see § Open OQs)
- `/v1/ready` — was stubbed; current state in admin-api not independently verified since schema fixes

---

## Exact next step

**Step 1 (do immediately):** Restart mcp-server and mock-backend with new Python images:
```sh
docker compose up -d --no-deps --build mcp-server mock-backend
docker compose ps mcp-server mock-backend   # wait for healthy
```

**Step 2:** Fix the 7 admin-ui test failures (see § Admin-UI test failures below). These are quick: `RestResource.key` returns the object itself; tests expect a string. The fix is likely in `admin-ui/src/lib/rest-resource.ts` — the `key` getter needs to return `this._key` (a string), not `this`.

**Step 3:** Create `tests/acceptance/ENDPOINT_COVERAGE.md` — the inventory matrix (path × method × source × test file × status codes). Template: one row per entry in the union of `docs/architecture/contracts/rest/openapi.yaml` paths and FastAPI routers. Columns: `path | method | source | test_file::test_fn | asserted_statuses | last_result`.

**Step 4:** Create `tests/integration/admin_api/` scaffold:
- `conftest.py` — testcontainers Postgres, run all Liquibase changelogs, create `mintkey_app` user, seed minimal data (one tenant, one operator with hashed password), yield engine/session.
- One test file per resource group (`test_auth.py`, `test_services.py`, `test_agents.py`, etc.).
- Each test boots admin-api against the testcontainer DB (no mocks for DB), exercises the endpoint, validates response against OpenAPI schema.

**Step 5:** Run `pytest tests/integration/admin_api/ -q` and fix failures until 100% green.

**Step 6:** Re-run full §9 verification suite; update this file.

---

## Admin-UI test failures (7 failures)

Command: `cd admin-ui && npm test`  
Result: 7 failed / 40 passed

Failing pattern (all same root cause):
```
AssertionError: expected RestResource{ _decorated: null, …(2) } to be 'services' // Object.is equality
```
Affected tests: `ServicesResource`, `CredentialsResource`, `AgentsResource`, `PermissionsResource`, `AuditResource`, `TenantsResource`, `ApiKeysResource` — all `has resource key` assertions.

Root cause: `admin-ui/src/lib/rest-resource.ts` `RestResource` class. Tests call `resource.key` and expect a string (e.g. `'services'`), but the getter returns the `RestResource` instance itself. Fix: ensure the `key` property returns the string key passed at construction (e.g. `this._key`), not `this`.

File to fix: `admin-ui/src/lib/rest-resource.ts`  
Test file: `admin-ui/tests/test_resources.test.ts`, `admin-ui/tests/test_api_keys.test.ts`

---

## Open OQs (blocking or decision-needed)

| OQ | Question | Blocking | Status |
|----|----------|----------|--------|
| OQ-ADMINJS-RO | Should `mintkey_app_ro` read-only role for AdminJS use `BYPASSRLS` or per-request `SET app.current_tenant`? ADR-0008 mandates RLS but doesn't specify the AdminJS read path. | Phase 2 (admin-ui resource lists) | Open — not in any ADR |
| OQ-SEED-STEPS-6-12 | Are seed-job steps 6–12 (AdminJS keypair, 4 service_identities, Broker keypair, Keycloak realm import, bootstrap_completed audit) actually implemented or still stubs? `docker logs mintkey-seed-job-1` needs inspection. | Phase 1 (stack fully wired), Phase 4 (data plane) | Open |
| OQ-MCP-PROTOCOL | ADR-0009 specifies MCP-over-SSE. Current mcp-server uses plain HTTP REST tools (`discovery_router`, `request_token_router`). If REST tools stay, ADR-0009 needs a superseding ADR or an OQ. | Phase 4 (data plane) | Open |

---

## Uncommitted state

All changes are in working tree. Staged at `git add -A` for the wip checkpoint commit.

Key new/modified files this session:
- `tests/unit/mcp_server/test_auth.py` — fixed `-> JSONResponse` annotation (PydanticUndefinedAnnotation)
- `tests/acceptance/test_multitenant_smoke.py` — added `proxy_call`/`proxy_hit`/`acknowledge_tamper` to `_STC_EXEMPT_HANDLERS`
- `scripts/e2e_smoke.py` — expanded from ~443 to ~901 lines, covering 34/35 admin-api endpoints
- `mcp-server/Dockerfile` + `mcp-server/requirements.txt` — real Python image (replaces nginx:alpine)
- `mock-backend/Dockerfile` — real Python image (replaces nginx:alpine)
- `docker-compose.yml` — wired mcp-server and mock-backend to real Python builds
- `tests/unit/admin_api/test_api_keys.py` — fixed `_MockDb.begin_nested()` (3 policy tests were failing)
- `tests/acceptance/openapi_snapshot.json` — updated with api_keys + proxy router entries
- `tests/acceptance/test_tenant_isolation.py` — added proxy exemptions

---

## Test suite snapshot (2026-05-11, pre-commit)

```
pytest tests/architecture/ -q  →  17 passed
pytest tests/acceptance/ -q    → 106 passed, 23 skipped
pytest tests/unit/ -q          → 142 passed
Total (excl. integration):       265 passed, 23 skipped, 0 failed

Go (all 4 services):  all go test ./... green
admin-ui npm test:    40 passed, 7 FAILED (RestResource.key issue)
```

---

## Resumability

If starting fresh: re-run `pytest tests/ -q --ignore=tests/integration`, then `cd admin-ui && npm test`, then `docker compose ps`. Fix first red item. Continue from **§ Exact next step**.
