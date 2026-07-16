# Tasks — Operator Management API

## 1. Contracts & ADR (land first)
- [ ] 1.1 ADR-0031 (status Proposed) + `docs/architecture/adrs/0031-…` symlink + `adr/README.md` index row.
- [ ] 1.2 Extend `docs/architecture/contracts/rest/openapi.yaml`: `/v1/operators` (GET, POST) +
      `/v1/operators/{operator_id}` (PATCH, DELETE); `Operator`, `CreateOperatorRequest`,
      `UpdateOperatorRequest`, `OperatorPage`, `OperatorStatus` schemas; `OperatorId` param. Verify
      `openapi-spec-validator`.
- [ ] 1.3 Extend `docs/architecture/contracts/events/audit-event.schema.json`:
      `operator.created` / `operator.updated` / `operator.deleted`.
- [ ] 1.4 `openspec validate operator-management --strict` passes.

## 2. admin-api (Python / FastAPI) — test-first
- [ ] 2.1 `api/operators.py`: `GET` list (RLS platform-admin view, `q`/`tenant_id`/cursor filters).
- [ ] 2.2 `POST` create by email; `IntegrityError → 409 duplicate_resource`; audit `operator.created`;
      never serialize `internal_password_hash`.
- [ ] 2.3 `PATCH /{operator_id}` (display_name / is_platform_admin / status) + audit `operator.updated`;
      `404 not_found` for unknown id.
- [ ] 2.4 `DELETE /{operator_id}` soft-deactivate (`status='disabled'`), idempotent `204`, audit
      `operator.deleted`.
- [ ] 2.5 `include_router(operators_router)` in `main.py`; update `tests/acceptance/openapi_snapshot.json`.
- [ ] 2.6 Unit tests green: happy / 409 dup email / 409 dup oidc_sub / no-hash-in-response /
      platform-admin-actor audit / RLS GUC set.

## 3. admin-ui (AdminJS BFF)
- [ ] 3.1 `resources/operators.ts` (RestResource + ResourceWithOptions, platform-admin `isVisible`);
      register in `index.ts`.
- [ ] 3.2 Promote (new) / edit / deactivate actions via `apiWrite` with `operatorOptsFromAdmin` (signed
      request + CSRF).
- [ ] 3.3 vitest `tests/test_operators.test.ts` green.

## 4. Gates & E2E
- [ ] 4.1 Re-run RLS + audit-coverage + openapi-parity + SQLi gates.
- [ ] 4.2 Playwright `e2e/tests/NN-operators.spec.ts` + `e2e/pages/operators.ts`: promote → list →
      patch role → deactivate; confirm audit chain + zero `internal_password_hash`.
- [ ] 4.3 Open PR against `main` with the issue-intake summary + pasted verification output.
