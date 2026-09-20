# Implementation Plan: Agent Access Requests

## Overview

Convert the design into a series of incremental coding steps for the `agent-access-requests` feature. The order is **contract-first** (P-4): wire surfaces land first and are CI-validated, then the schema + SQLAlchemy mirror, then the admin-api service/router, then the MCP tools, then the Admin Console Requests_Review_Area, then observability, then the mandatory Playwright e2e, and finally the add-only architecture/red-team verification.

The feature is **strictly additive** (Req 14): every task adds new files or appends new members to existing closed contracts/enums; no existing endpoint, tool, table, audit event, request/response schema, or test is modified, renamed, or deleted. Approval reuses the existing grant, service-registration, and credential machinery through their current interfaces rather than reimplementing them.

Languages follow the pinned tech stack — admin-api and mcp-server are Python 3.12 (FastAPI, SQLAlchemy 2.x async, Pydantic v2, Hypothesis), the Admin Console is Node 20 (AdminJS BFF, vitest, Playwright). No pseudocode is used in the design, so no implementation-language selection is required.

Property-based tests use `hypothesis` (already present — see `.hypothesis/`), run a minimum of 100 iterations, and are tagged `# Feature: agent-access-requests, Property {N}: {property_text}`.

## Tasks

- [x] 1. Contract-first wire surfaces (P-4, Req 13)
  - [x] 1.1 Add the 5 REST endpoints to the canonical OpenAPI
    - In `docs/architecture/contracts/rest/openapi.yaml` (OAS 3.1) define, under `/v1/tenants/{tenant_id}/access-requests`: `GET /` (list; `status` + `kind` filters; `created_at desc`), `GET /{request_id}` (detail), `POST /{request_id}/approve` (approve/finalize; integration secret body marked `x-mintkey-sensitive`), `POST /{request_id}/reject` (reason), `POST /{request_id}/test` (Connection_Test).
    - Define the `AccessRequest` response schema per design §Wire Contracts; express every nullable field as `type: [<T>, "null"]` with zero `nullable: true` occurrences.
    - State-changing routes require `AdminUiSignedRequest` + operator session (ADR-0019).
    - _Requirements: 13.1, 13.4, 4.1, 4.2, 5, 6.3, 6.5, 7, 8_

  - [x] 1.2 Add the 4 MCP tools to the canonical tools contract
    - In `docs/architecture/contracts/mcp/tools.yaml` define `request_access` `{service_id, action}`, `propose_integration` `{name, base_url, auth_scheme, openapi_url?, config}` (reuse the closed `#/$defs/auth_scheme` enum), `request_share` `{service_id, action, target_agent_id}`, `list_my_requests` `{status?, kind?, after?, limit?}`.
    - Each tool declares **no** `tenant_id` argument (tenant resolved from Agent API Key auth context, ADR-0009).
    - _Requirements: 13.2, 1.1, 1.7, 2.1, 3.1_

  - [x] 1.3 Add the audit event types + `target_type` to the events contract
    - In `docs/architecture/contracts/events/audit-event.schema.json` add `access_request` to the closed `target_type` enum and define `access_request.created` / `.approved` / `.rejected` / `.expired` conforming to the existing envelope + per-tenant hash chain (`prev_hash` + `hash`); payloads are identifier/metadata-only (no secret/denylisted values).
    - _Requirements: 10.2, 10.3, 13.1_

  - [x] 1.4 Add the 7 new error codes to both closed enums
    - Add `request_not_found`, `request_not_pending`, `already_granted`, `request_already_pending`, `secret_field_not_allowed`, `missing_secret_material`, `reason_required` to the `mintkey:code` enum in `openapi.yaml` **and** the `error_code` enum in `tools.yaml`, so every feature code is a member of both.
    - _Requirements: 13.3_

  - [x] 1.5 Contract validation checks (add-only)
    - Run `openapi-spec-validator` + Redocly lint on `openapi.yaml`; `Draft202012Validator.check_schema` on the audit event schema; YAML lint on `tools.yaml`.
    - Add a check asserting every feature error code appears in both closed enums.
    - Adds NEW test/CI-check files only; modifies no existing test.
    - _Requirements: 13.1, 13.3, 13.5, 13.6_

- [x] 2. Database schema and SQLAlchemy mirror (Req 12)
  - [x] 2.1 Liquibase changeset 030 for `access_requests` with RLS
    - Create `apps/admin-api/db/changelog/030-access-requests.yaml` per design §Data Models: columns `id`, `tenant_id UUID NOT NULL`, `kind`, `status`, `requesting_agent_id`, `service_id`, `action`, `target_agent_id`, `share_direction`, `proposed_config JSONB`, `reason`, `expires_at`, `created_at`, `resolved_at`, `created_by`, `resolved_by`.
    - `CHECK` constraints enumerating `kind` / `status` / `share_direction`; FKs to `tenants`/`agents`/`services`; indexes `idx_access_requests_tenant` and a partial index on `(tenant_id, status)` for the pending-list + sweep.
    - Enable RLS and create the `tenant_isolation` policy **in the same changeset** (follow `027-agent-secrets.yaml`); `preConditions … onFail: MARK_RAN`.
    - Register the changeset in `db.changelog-master.yaml`.
    - Verify: run Liquibase against a fresh test DB; `information_schema.columns` confirms schema; `pg_policies` confirms the `tenant_isolation` policy references `current_setting('app.current_tenant')`.
    - _Requirements: 12.1, 12.5, 9.1_

  - [x] 2.2 SQLAlchemy `AccessRequest` mapped model + Pydantic models
    - Add the `AccessRequest` `Mapped` class to `packages/python/mintkey-models` mirroring the **introspected** schema (does not define it, P-8).
    - Add the `request_` prefixed-ULID wire helper usage (reuse existing `to_wire_id`) and Pydantic v2 request/response models in the admin-api service layer.
    - _Requirements: 12.6, 13.4_

  - [x] 2.3 SQLAlchemy mirror diff check (add-only)
    - Run `sqlacodegen` diff after the 030 changeset; assert no drift between the mirror and the introspected schema.
    - Adds a NEW check only; modifies no existing test.
    - _Requirements: 12.6_

- [x] 3. Admin API service layer — create + validation (Req 1, 2, 3)
  - [x] 3.1 Pure validation helpers
    - In `apps/admin-api/src/admin_api/services/access_requests.py` implement the secret-denylist matcher (`*_secret`, `*_password`, `*_passphrase`, `private_key`, `token`, `api_key`), the `ssh://host:port` `base_url` validator, the `openapi_url` HTTPS+SSRF-allowlist check (reuse existing SSRF check), and the RFC-3339 `expires_at = created_at + 30d` computation.
    - _Requirements: 2.4, 2.5, 2.6, 2.8, 2.9, 9.1_

  - [x] 3.2 Unit tests for validation helpers (add-only)
    - Concrete examples/edge cases for each helper (denylist match/miss, valid/invalid SSH URL, non-HTTPS/SSRF-blocked openapi_url, 30-day delta, `request_` ULID formatter). NEW test file only.
    - _Requirements: 2.4, 2.5, 2.6, 2.8, 2.9, 9.1_

  - [x] 3.3 Create logic for all three kinds
    - Implement `create` branching by kind with all validations: access (`service_id`/`action` present, service exists in tenant, not already granted, no duplicate pending); integration (`name`/`base_url`/`auth_scheme` present, enum-valid, denylist gate, SSH rules, openapi_url check, store non-secret `proposed_config`, no `services` row); share (present fields, no self-target, service+target exist, outbound requires requester's grant, target not already granted, `share_direction` recorded).
    - Persist with tenant GUC set; return `request_` id.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x] 3.4 Property tests — create shape, denylist, invalid inputs, duplicate pending
    - **Property 7: The config secret-denylist gate rejects any secret field** — _Validates: Requirements 2.4_
    - **Property 13: Created requests have the correct kind-specific shape** — _Validates: Requirements 1.1, 2.7, 3.1, 3.2, 3.9_
    - **Property 14: Invalid create/reject inputs are rejected with no row change** — _Validates: Requirements 1.3, 1.5, 2.2, 2.3, 2.5, 2.6, 3.3, 3.4, 3.7, 3.8, 8.2_
    - **Property 16: Duplicate pending requests are rejected** — _Validates: Requirements 1.6_
    - Hypothesis, ≥100 iterations, tagged; NEW test file only.

  - [x] 3.5 List + get with tenant scoping, filters, ordering
    - Implement `list` (tenant-scoped via RLS, optional `status`/`kind` filters, `created_at desc`, required fields) and `get` (full detail; cross-tenant `request_id` → `request_not_found`; integration detail exposes blank operator-supplied secret fields).
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [x] 3.6 Property test — listing subset/order/scope
    - **Property 15: Listing returns the correct tenant-scoped, filtered, ordered subset** — _Validates: Requirements 1.7, 4.1, 4.2, 8.4_
    - Hypothesis, ≥100 iterations, tagged; NEW test file only.

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Admin API — approve / reject / test / expire (Req 5, 6, 7, 8, 9, 10)
  - [x] 5.1 Approve branching by kind (reuse existing machinery)
    - Implement `approve`: guard `pending` else `request_not_pending`; access → create grant `(agent, service, action)` via the **existing** grant service; share → create grant `(target_agent, service, action)` (idempotent if it already exists); integration finalize → create `services` row + store secret via the **existing** service-registration + credential/Vault path (operator-edited config applied). Set `status = approved`, `resolved_at`/`resolved_by` from session. Publish grant change on `mintkey:agent` (≤5s, P-9).
    - Errors: `request_not_found`, `service_not_found` (share, at approval), `missing_secret_material` (blank secret), `vault_unavailable` (no service/secret persisted).
    - _Requirements: 5.1, 5.5, 5.6, 5.7, 6.2, 6.5, 6.6, 6.7, 7.1, 7.3, 7.4, 7.5, 14.4_

  - [x] 5.2 Property tests — state machine, grant outcomes, terminal artifacts
    - **Property 3: Approve and reject are legal only from `pending`** — _Validates: Requirements 5.6, 7.4, 9.5_
    - **Property 4: Terminal requests produce no side artifacts** — _Validates: Requirements 8.3, 9.4_
    - **Property 5: Approving a pending grant-request yields exactly the requested grant** — _Validates: Requirements 5.1, 7.1_
    - **Property 6: Approval is idempotent when the grant already exists** — _Validates: Requirements 7.5_
    - **Property 8: Operator config edits override agent-proposed values** — _Validates: Requirements 6.2_
    - Hypothesis, ≥100 iterations, tagged; NEW test file only.

  - [x] 5.3 Reject with reason
    - Implement `reject`: require non-empty, ≤1000-char `reason` else `reason_required`; guard `pending` else `request_not_pending`; cross-tenant → `request_not_found`; set `status = rejected`, store `reason`; create no grant/service/credential.
    - _Requirements: 8.1, 8.2, 8.3, 8.6, 8.7_

  - [x] 5.4 Connection_Test (10s timeout, secret-free diagnostic)
    - Implement `POST .../{request_id}/test` reusing the transient-test machinery behind `POST /services/test-transient`: perform an upstream handshake per `auth_scheme` (REST schemes hit health/base path; SSH schemes open TCP+SSH to `ssh://host:port`) with a 10s timeout and egress allowlist; return `{ok, status_code, latency_ms, diagnostic}` with no secret material; timeout → fail result noting timeout.
    - _Requirements: 6.3, 6.4_

  - [x] 5.5 Audit emission at every state change (chokepoint, atomic)
    - Route created/approved/rejected/expired through the single `audit.emit()` helper inside the same DB transaction; on approval additionally emit `agent.permission.granted` / `service.registered` / `credential.registered`; set `actor_type` (`agent`/`operator`/`system`) with operator identity from the validated session; roll back the whole transaction if audit fails.
    - _Requirements: 5.4, 7.1, 7.2, 7.6, 10.1, 10.4, 10.5, 10.6_

  - [x] 5.6 Property tests — audit coverage, actor type, atomicity, secret non-leak
    - **Property 1: The operator secret never leaks anywhere secret-free** (red-team canary across row, logs, audit payloads, span attrs, test diagnostic, agent response; vault-down variant) — _Validates: Requirements 6.1, 6.3, 6.7, 10.3, 11.3, 11.5_
    - **Property 10: Every state change emits its audit event through the chokepoint** — _Validates: Requirements 5.4, 7.1, 10.1, 10.4_
    - **Property 11: Audit actor type matches the trigger** — _Validates: Requirements 10.5_
    - **Property 12: Audit failure aborts the state change atomically** — _Validates: Requirements 10.6_
    - Hypothesis, ≥100 iterations, tagged; NEW test file only.

  - [x] 5.7 Expiration — lazy-on-read guard + scheduled sweep
    - Implement lazy-on-read: any read/mutation loading a `pending` row where `now() >= expires_at` treats it as `expired` (approve/reject → `request_not_pending`).
    - Implement the scheduled sweep (a small `access-request-expiry-job` / admin-api cron following the `audit-verify-job` precedent) flipping `pending → expired` and emitting one `access_request.expired` (`actor_type: system`) per row through `audit.emit()`.
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 10.1, 10.5_

  - [x] 5.8 Property test — expiration boundary
    - **Property 9: Expiration boundary is exact and 30 days** — _Validates: Requirements 9.1, 9.2, 9.3_
    - Hypothesis, ≥100 iterations, tagged; NEW test file only.

- [x] 6. Admin API router + auth wiring (Req 5, 12)
  - [x] 6.1 `api/access_requests.py` router
    - Create the router mounting the 5 endpoints alongside existing routers; reads set the tenant GUC from the validated session; writes require the signed request (ADR-0019) and derive effective identity (audit `actor_id`, tenant GUC) from the **session**, not the JWT body; reject when tenant context cannot be resolved.
    - Mark secret-bearing bodies `x-mintkey-sensitive` (excluded from body logging, ADR-0026 D7 precedent).
    - _Requirements: 5.2, 5.3, 12.2, 12.3, 12.4_

  - [x] 6.2 Property test — tenant isolation (add-only, architecture-flavored)
    - **Property 2: Tenant isolation holds for every cross-tenant reference** (fuzz cross-tenant `request_id`s + missing-GUC transactions across all reads/mutations) — _Validates: Requirements 4.4, 5.5, 8.6, 12.2, 12.3, 12.4_
    - Hypothesis, ≥100 iterations, tagged; NEW test file only.

  - [x] 6.3 Integration tests — auth + change-channel + Connection_Test (add-only)
    - Missing/mismatched session vs signed JWT → unauthorized, no change; approve publishes grant change on `mintkey:agent` observed ≤5s; revoke publishes `agent.permission.revoked`; Connection_Test pass / 401 / 10s timeout against a stub upstream. `testcontainers`; NEW test files only.
    - _Requirements: 5.2, 5.3, 5.7, 6.3, 6.4, 7.2, 7.6_

- [x] 7. MCP Server tools (Req 1, 2, 3, 13)
  - [x] 7.1 Implement the 4 tool handlers
    - Add `tools/request_access.py`, `tools/propose_integration.py`, `tools/request_share.py`, `tools/list_my_requests.py` following the existing tool pattern; each resolves `agent_id`/`tenant_id` from the Bearer Agent API Key context and calls the admin-api service layer; no `tenant_id` argument accepted.
    - _Requirements: 1.1, 1.7, 2.1, 3.1, 3.2, 13.2_

  - [x] 7.2 Integration tests for MCP tools (add-only)
    - Each tool creates the correct kind/shape and echoes `request_id`/`status`; `list_my_requests` returns only the caller agent's tenant-scoped rows. NEW test files only.
    - _Requirements: 1.1, 1.7, 2.1, 3.1, 8.4_

- [x] 8. Admin Console — Requests_Review_Area (Req 4, 6, 8)
  - [x] 8.1 BFF routes
    - Add `/admin/api/access-requests/*` BFF routes in `apps/admin-ui/` proxying to admin-api via `apiWrite()` (session cookie + signed JWT); secret-bearing bodies are not logged; no DB connection (ADR-0019).
    - _Requirements: 4.7, 6.1_

  - [x] 8.2 List + detail pages (separated navigation section)
    - Add a dedicated AdminJS navigation section clearly separated from Services/Agents/Permissions (same BFF pattern as `budget-management-ui`). List page shows pending requests with `kind`, `status`, requesting agent, target summary, `created_at`, `expires_at` + `status`/`kind` filters. Detail page shows full request; integration proposals render non-secret config + empty, operator-supplied-labelled secret inputs.
    - _Requirements: 4.5, 4.6_

  - [x] 8.3 Actions — Approve / Reject / Test / Finalize
    - Approve control; Reject with a reason textbox that **blocks submission when empty**; for integrations: editable non-secret config fields, a **Test connection** control showing the Connection_Test result, and a **Finalize** control **enabled only after required secrets are supplied**.
    - _Requirements: 6.8, 8.5_

  - [x] 8.4 vitest unit tests for UI guards (add-only)
    - Reason-required guard blocks empty submit; finalize-enabled guard toggles on secret presence. NEW test files only.
    - _Requirements: 6.8, 8.5_

- [x] 9. Observability — OTel tracing + metrics (Req 11)
  - [x] 9.1 Trace propagation MCP → admin-api → admin-ui
    - Propagate W3C `traceparent` on the MCP→admin-api and admin-ui→admin-api calls so the spans (`mcp.request_access`, `adminapi.access_request.create`, `adminui.approve`, `adminapi.access_request.approve`, `grant.create`) share one trace ID; stamp `trace_id` on the audit envelope.
    - _Requirements: 11.1_

  - [x] 9.2 Metrics + span attribute allowlist + structured logs
    - Increment `access_request_created_total` / `_approved_total` / `_rejected_total` / `_expired_total` labelled `kind` + `tenant_id`; restrict span attributes to the allowlist (omit any `*_token`/`*_secret`/`*_password`/`*_passphrase`/`Authorization`/`Cookie`); emit structured logs carrying `request_id`, `kind`, `status` only.
    - _Requirements: 11.2, 11.3, 11.4, 11.5_

  - [x] 9.3 Integration test — single trace ID + metric increments (add-only)
    - Assert one trace ID across MCP → admin-api → admin-ui approval and per-transition counter increments. NEW test file only.
    - _Requirements: 11.1, 11.2_

- [x] 10. MANDATORY headless Admin UI end-to-end test (Req 15)
  - [x] 10.1 Playwright e2e spec — Approve + Reject-with-reason with artifacts
    - Add a NEW Playwright spec under the repo's UI test location, aligned with `.github/workflows/playwright.yml` (no existing test touched). It: logs into the Admin Console and navigates to the Requests_Review_Area (fail if not reached within 30s); asserts the pre-seeded pending request is rendered by its `request_id` with status "pending"; in an **Approve** case asserts the displayed status changes to "approved"; in a **separate Reject-with-reason** case submits a non-empty reason and asserts status "rejected" with the reason displayed; captures **screenshot + Playwright trace** at (a) first-visible pending and (b) post-action status; uploads both as retained CI artifacts; fails if the Requests_Review_Area or its Approve/Reject controls are absent or non-functional.
    - Add the seed step for the pending request used by the test.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9, 15.10_

- [x] 11. Architecture / verification tests (add-only) (Req 10, 12, 13, 14)
  - [x] 11.1 RLS + audit coverage extensions
    - Extend `tests/architecture/test_rls_coverage.py` (append) to assert `access_requests` has a `tenant_isolation` policy referencing `current_setting('app.current_tenant')`; extend `tests/architecture/test_audit_coverage.py` (append) to assert the new state-change handlers route through `audit.emit()`. Add-only assertions; no existing test rewritten.
    - _Requirements: 10.1, 12.1_

  - [x] 11.2 Contract round-trip + red-team grep
    - Assert the FastAPI-emitted OpenAPI is structurally equivalent to the checked-in `openapi.yaml` (round-trip diff, build fails on drift); red-team grep confirms secret fingerprints are absent from all log/span emissions on this path (pairs with Property 1). NEW check files only.
    - _Requirements: 13.5, 13.6, 11.3, 11.5_

  - [x] 11.3 Backwards-compatibility guard
    - Run the full existing suite; assert zero new failures and zero newly-skipped tests; confirm no existing wire surface/schema/test changed. Any forced change to an existing surface is surfaced as an `OQ-NNN` blocking issue rather than applied.
    - _Requirements: 14.1, 14.2, 14.3, 14.5_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test/verification sub-tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirement sub-clauses and/or the correctness property it satisfies for traceability.
- Contracts land first (P-4); the CI round-trip diff gates implementation against them.
- Approval **reuses** the existing grant, service-registration, and credential machinery through their current interfaces — it does not reimplement them (Req 14.4).
- Property 1 (secret never leaks) and Property 2 (tenant isolation) double as red-team / architecture tests.
- Every test task adds NEW files only; no existing test is modified, renamed, or deleted (Req 14.2–14.3). Architecture tests are extended by appending assertions.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["1.5", "2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3"] },
    { "id": 5, "tasks": ["3.4", "3.5"] },
    { "id": 6, "tasks": ["3.6", "5.1", "5.3", "5.4"] },
    { "id": 7, "tasks": ["5.2", "5.5", "5.7"] },
    { "id": 8, "tasks": ["5.6", "5.8", "6.1"] },
    { "id": 9, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 10, "tasks": ["7.2", "8.1"] },
    { "id": 11, "tasks": ["8.2", "8.3"] },
    { "id": 12, "tasks": ["8.4", "9.1", "9.2"] },
    { "id": 13, "tasks": ["9.3", "10.1"] },
    { "id": 14, "tasks": ["11.1", "11.2", "11.3"] }
  ]
}
```
