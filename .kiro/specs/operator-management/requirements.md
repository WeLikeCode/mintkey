# Operator Management — Requirements

## Status
Proposed — 2026-07-16. Traces to ADR-0031 and `openspec/changes/operator-management/`.

## Introduction
Adds a REST + Admin-UI surface to manage Mintkey operators (`public.operators`): promote a Keycloak
realm-`mintkey` user to an operator, list operators, update role/status, and deactivate one. All
endpoints are platform-admin-gated, signed-request authenticated, and audited. admin-api does not call
Keycloak; `oidc_sub` binds lazily on first OIDC login (ADR-0020).

## Glossary
- **Operator**: a human identity in `public.operators` who authenticates via Keycloak OIDC.
- **Platform admin**: an operator with `is_platform_admin = true`.
- **Promote**: create an `operators` row (+ `operator_tenant_memberships`) for an existing Keycloak user.
- **Wire ID**: `op_<26-char Crockford ULID>`, derived from the `operators.id` UUID (ADR-0017.10, ADR-0031 D2).

## Error Codes
- `duplicate_resource` (409) — `(tenant_id, email)` or `oidc_sub` already exists.
- `not_found` (404) — no operator with that id.
- `invalid_id` (422) — malformed `op_…` wire id.
- `validation_failed` (400) — body fails schema validation.
- `unauthenticated` (401) / `permission_denied` (403) — missing session / not a platform admin.

## Requirements

### Requirement 1: Promote a Keycloak user to an operator

**User Story:** As a platform admin, I want to promote an existing Keycloak realm-`mintkey` user to a
Mintkey operator, so that they can administer a tenant without a manual DB write.

#### Acceptance Criteria
1. WHEN a platform admin submits `{ email, display_name?, oidc_sub?, is_platform_admin?, tenant_id }`
   to `POST /v1/operators`, AND `email` is unique within `(tenant_id, email)`, AND `oidc_sub` is unique
   where present, THEN the Admin REST API SHALL insert one row into `public.operators`, insert an
   `operator_tenant_memberships` row (`role='Admin'`, `ON CONFLICT DO NOTHING`), emit audit event
   `operator.created`, and return HTTP 201 with the operator resource whose `id` is `op_`-prefixed and
   which SHALL NOT contain `internal_password_hash`.
2. WHEN the `(tenant_id, email)` pair already exists, THE Admin REST API SHALL return HTTP 409
   `duplicate_resource` and SHALL NOT create a row.
3. IF `oidc_sub` collides with an existing operator, THEN THE Admin REST API SHALL return HTTP 409
   `duplicate_resource`.
4. WHERE `oidc_sub` is omitted, THE Admin REST API SHALL store `NULL` and SHALL NOT call Keycloak; the
   binding is deferred to the operator's first OIDC login (ADR-0020).
5. THE create endpoint SHALL require a platform-admin `mintkey_session`, a valid `AdminUiSignedRequest`,
   and the CSRF header; the audit `actor_id` SHALL be taken from the session, not the request body.

### Requirement 2: List operators

**User Story:** As a platform admin, I want to list operators, so that I can review who has access.

#### Acceptance Criteria
1. WHEN a platform admin GETs `/v1/operators`, THE Admin REST API SHALL return HTTP 200 with a
   cursor-paginated `OperatorPage` computed under the platform-admin RLS view
   (`app.platform_admin_view='on'`), and no item SHALL contain `internal_password_hash`.
2. WHERE `tenant_id` and/or `q` query parameters are supplied, THE Admin REST API SHALL filter by tenant
   and by a case-insensitive substring over `email` and `display_name` respectively.

### Requirement 3: Update an operator's role and status

**User Story:** As a platform admin, I want to change an operator's display name, platform-admin flag, or
status, so that I can manage privileges over time.

#### Acceptance Criteria
1. WHEN a platform admin submits `{ display_name?, is_platform_admin?, status? }` to
   `PATCH /v1/operators/{operator_id}` for an existing operator, THEN THE Admin REST API SHALL update
   only the supplied columns, emit `operator.updated`, and return HTTP 200 with the updated resource.
2. IF `operator_id` does not resolve to an existing operator, THEN THE Admin REST API SHALL return HTTP
   404 `not_found`.
3. IF `operator_id` is not a valid `op_…` wire id, THEN THE Admin REST API SHALL return HTTP 422
   `invalid_id`.

### Requirement 4: Deactivate an operator

**User Story:** As a platform admin, I want to deactivate an operator, so that a departed admin can no
longer sign in.

#### Acceptance Criteria
1. WHEN a platform admin calls `DELETE /v1/operators/{operator_id}` for an active operator, THEN THE
   Admin REST API SHALL set `status='disabled'` (soft delete; no hard `DELETE`), emit `operator.deleted`,
   and return HTTP 204.
2. WHEN the operator is already disabled or absent, THE Admin REST API SHALL return HTTP 204
   (idempotent) and SHALL NOT emit a duplicate `operator.deleted`.

### Requirement 5: Admin UI operators surface

**User Story:** As a platform admin, I want an Operators screen, so that I can promote/manage operators
without curl.

#### Acceptance Criteria
1. THE Admin UI SHALL expose an `operators` resource visible only WHEN `currentAdmin.isPlatformAdmin`
   is true, listing `email`, `display_name`, `is_platform_admin`, `status`, `created_at`.
2. WHEN a platform admin submits the "promote operator" form, THE Admin UI SHALL POST to `/v1/operators`
   via the signed-request client (`apiWrite` + `operatorOptsFromAdmin`) and surface the API success or
   `title` error as a notice.
