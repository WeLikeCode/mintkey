# Operator Management — Tasks

Traceability: each task cites the Requirement/Acceptance-Criterion (R#.AC#) it satisfies. Mirrors
`openspec/changes/operator-management/tasks.md`.

Status: implemented on `main` by PR #273 (c025fa4): `apps/admin-api/src/admin_api/api/operators.py` (router in
`main.py`), `tests/unit/admin_api/test_operators.py`, `apps/admin-ui/src/resources/operators.ts`,
`apps/admin-ui/tests/test_operators.test.ts`, `apps/admin-ui/e2e/tests/30-operators.spec.ts`, the `/v1/operators`
paths of `openapi.yaml`, the `operator.*` audit events and ADR-0031. `_Requirements:_` lines map each task to the
acceptance criteria (Req N.M) of `requirements.md`, from the task's own R#.AC# reference.

## 1. Contracts & ADR (land first)
- [x] 1.1 ADR-0031 + `adrs/` symlink + `adr/README.md` index row. (ADR-0031) [docs]
- [x] 1.2 `openapi.yaml`: `/v1/operators` GET/POST + `/{operator_id}` PATCH/DELETE + schemas +
      `OperatorId` param. (R1–R4)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3_
- [x] 1.3 `audit-event.schema.json`: `operator.created/.updated/.deleted`. (R1.1, R3.1, R4.1)
  - _Requirements: 1.1, 3.1, 4.1_
- [x] 1.4 `openspec validate operator-management --strict`. [chore]

## 2. admin-api (test-first)
- [x] 2.1 `GET /v1/operators` list under platform-admin RLS; `q`/`tenant_id` filters. (R2)
  - _Requirements: 2.1, 2.2_
- [x] 2.2 `POST /v1/operators` create-by-email; dup email/oidc_sub → 409; audit; no hash. (R1)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
- [x] 2.3 `PATCH /{operator_id}`; 404/422; audit `operator.updated`. (R3)
  - _Requirements: 3.1, 3.2, 3.3_
- [x] 2.4 `DELETE /{operator_id}` soft-deactivate; idempotent 204; audit `operator.deleted`. (R4)
  - _Requirements: 4.1, 4.2, 4.3_
- [x] 2.5 `include_router` + refresh `tests/acceptance/openapi_snapshot.json`. (R1–R4)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3_
- [x] 2.6 Unit tests: happy / 409 dup email / 409 dup oidc_sub / no-hash / audit actor / RLS GUC. (R1–R4)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3_

## 3. admin-ui
- [x] 3.1 `resources/operators.ts` + register in `index.ts`; platform-admin `isVisible`. (R5.1)
  - _Requirements: 5.1_
- [x] 3.2 promote/edit/deactivate actions via `apiWrite` (signed request + CSRF). (R5.2)
  - _Requirements: 5.2_
- [x] 3.3 vitest `tests/test_operators.test.ts`. (R5)
  - _Requirements: 5.1, 5.2_

## 4. Gates & E2E
- [x] 4.1 arch gates green (openapi-parity, audit-coverage, RLS, SQLi). [chore]
- [x] 4.2 Playwright `NN-operators.spec.ts` + `pages/operators.ts`: promote→list→patch→deactivate. (R1–R5)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 5.1, 5.2_
- [x] 4.3 Open PR to `main` with issue-intake + pasted verification output + exit codes. [chore]
