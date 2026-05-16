# Issue Intake — 2026-05-16-openapi-parity

## Problem statement

The CI snapshot test `test_openapi_parity_snapshot` fails because two routers diverged from the stored snapshot: (1) the `health` router's first inline route is now `/metrics` (not `/v1/health` as stored), and (2) a new `service_templates` router with prefix `/v1/service-templates` was added to `main.py` but never captured in the snapshot.

## User-visible symptom

```
FAILED tests/acceptance/test_openapi_parity.py::TestRouterStructure::test_openapi_parity_snapshot
AssertionError: Router prefix snapshot mismatch.
Current : {"health": "/metrics", "service_templates": "/v1/service-templates", ...}
Snapshot: {"health": "/v1/health", ...}
```

## Expected behavior

The snapshot matches the runtime router prefix set; all 5 tests in `test_openapi_parity.py` pass.

## Evidence

- `tests/acceptance/openapi_snapshot.json` — stale snapshot from before `service_templates` was added and before `/metrics` became the first route in `health.py`.
- `admin-api/src/admin_api/api/health.py` — `router = APIRouter()` (no prefix); first `@router.get` is `/metrics`.
- `admin-api/src/admin_api/api/service_templates.py` — `router = APIRouter(prefix="/v1/service-templates")`.
- `admin-api/src/admin_api/main.py` — `service_templates_router` is registered.

## Scope

`tests/acceptance/openapi_snapshot.json` only.

## Out of scope

Router code, openapi.yaml, accepted ADRs, all other tests.

## Risk level

CI (snapshot test failure); no production risk — the router code is correct.

## Verification target

```
cd admin-api && uv run pytest ../tests/acceptance/test_openapi_parity.py -v
# all 5 tests pass, exit 0
```

## Owner decisions needed

None — the router code (runtime truth) is correct; the snapshot was simply stale.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line or command)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (or "none")
