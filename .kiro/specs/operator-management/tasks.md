# Operator Management — Tasks

Traceability: each task cites the Requirement/Acceptance-Criterion (R#.AC#) it satisfies. Mirrors
`openspec/changes/operator-management/tasks.md`.

## 1. Contracts & ADR (land first)
- [ ] 1.1 ADR-0031 + `adrs/` symlink + `adr/README.md` index row. (ADR-0031)
- [ ] 1.2 `openapi.yaml`: `/v1/operators` GET/POST + `/{operator_id}` PATCH/DELETE + schemas +
      `OperatorId` param. (R1–R4)
- [ ] 1.3 `audit-event.schema.json`: `operator.created/.updated/.deleted`. (R1.1, R3.1, R4.1)
- [ ] 1.4 `openspec validate operator-management --strict`.

## 2. admin-api (test-first)
- [ ] 2.1 `GET /v1/operators` list under platform-admin RLS; `q`/`tenant_id` filters. (R2)
- [ ] 2.2 `POST /v1/operators` create-by-email; dup email/oidc_sub → 409; audit; no hash. (R1)
- [ ] 2.3 `PATCH /{operator_id}`; 404/422; audit `operator.updated`. (R3)
- [ ] 2.4 `DELETE /{operator_id}` soft-deactivate; idempotent 204; audit `operator.deleted`. (R4)
- [ ] 2.5 `include_router` + refresh `tests/acceptance/openapi_snapshot.json`. (R1–R4)
- [ ] 2.6 Unit tests: happy / 409 dup email / 409 dup oidc_sub / no-hash / audit actor / RLS GUC. (R1–R4)

## 3. admin-ui
- [ ] 3.1 `resources/operators.ts` + register in `index.ts`; platform-admin `isVisible`. (R5.1)
- [ ] 3.2 promote/edit/deactivate actions via `apiWrite` (signed request + CSRF). (R5.2)
- [ ] 3.3 vitest `tests/test_operators.test.ts`. (R5)

## 4. Gates & E2E
- [ ] 4.1 arch gates green (openapi-parity, audit-coverage, RLS, SQLi).
- [ ] 4.2 Playwright `NN-operators.spec.ts` + `pages/operators.ts`: promote→list→patch→deactivate. (R1–R5)
- [ ] 4.3 Open PR to `main` with issue-intake + pasted verification output + exit codes.
