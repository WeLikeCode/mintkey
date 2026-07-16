# Operator Management

## ADDED Requirements

### Requirement: Platform admin can promote a Keycloak user to an operator
An authenticated platform admin SHALL create an operator via `POST /v1/operators` with body
`{ email, display_name?, oidc_sub?, is_platform_admin?, tenant_id }`. `email` MUST be unique within
`(tenant_id, email)` and `oidc_sub` MUST be unique where present. The operation MUST emit
`operator.created`. The response MUST NOT contain `internal_password_hash`. admin-api MUST NOT call
Keycloak; when `oidc_sub` is absent it is bound lazily on the operator's first OIDC login.

#### Scenario: Successful promotion
- **WHEN** a platform admin POSTs a valid `{ email, tenant_id }` (optionally `oidc_sub`)
- **THEN** an operator row is created, `operator.created` is emitted, and the `201` response
  contains the operator metadata (with an `op_`-prefixed id) and no `internal_password_hash` field

#### Scenario: Duplicate email rejected
- **WHEN** a platform admin POSTs an `email` already present for that `tenant_id`
- **THEN** the request returns `409 duplicate_resource` and no row is created

#### Scenario: Duplicate oidc_sub rejected
- **WHEN** a platform admin POSTs an `oidc_sub` already bound to another operator
- **THEN** the request returns `409 duplicate_resource` and no row is created

### Requirement: Platform admin can list operators
An authenticated platform admin SHALL list operators via `GET /v1/operators`, optionally filtered by
`tenant_id` and a case-insensitive `q` substring over `email`/`display_name`, paginated by cursor.
The response MUST NOT contain `internal_password_hash`.

#### Scenario: List across tenants
- **WHEN** a platform admin GETs `/v1/operators`
- **THEN** a `200` page of operators is returned using the platform-admin RLS view

### Requirement: Platform admin can update an operator's role and status
An authenticated platform admin SHALL update an operator via `PATCH /v1/operators/{operator_id}` with
`{ display_name?, is_platform_admin?, status? }`, emitting `operator.updated`.

#### Scenario: Grant platform-admin
- **WHEN** a platform admin PATCHes `{ is_platform_admin: true }`
- **THEN** the flag is set, `operator.updated` is emitted, and the response reflects the change

#### Scenario: Unknown operator
- **WHEN** a PATCH targets an operator id that does not exist
- **THEN** the request returns `404 not_found`

### Requirement: Platform admin can deactivate an operator
`DELETE /v1/operators/{operator_id}` SHALL soft-deactivate the operator (`status='disabled'`) and emit
`operator.deleted` when a row changed. It MUST NOT hard-delete (`sessions` and
`operator_tenant_memberships` FK-reference `operators(id)`). It is idempotent for an already-disabled
operator (`204`, no duplicate event) but returns `404 not_found` for an id that does not resolve to an
existing operator.

#### Scenario: Deactivate
- **WHEN** a platform admin deletes an active operator
- **THEN** the operator's `status` becomes `disabled`, it can no longer establish a session, and
  `operator.deleted` is emitted

#### Scenario: Already disabled (idempotent)
- **WHEN** a platform admin deletes an operator whose `status` is already `disabled`
- **THEN** the request returns `204` and no duplicate `operator.deleted` is emitted

#### Scenario: Unknown operator
- **WHEN** a DELETE targets an operator id that does not exist
- **THEN** the request returns `404 not_found`

### Requirement: Operator writes require platform-admin session + signed request
Every state-changing operator call MUST require the `mintkey_session` cookie of a platform admin, a
valid `AdminUiSignedRequest`, and the double-submit CSRF header (ADR-0019). The audit `actor_id` MUST
come from the session, not from any JWT body.

#### Scenario: Non-platform-admin rejected
- **WHEN** a create/patch/delete arrives from a session whose operator is not `is_platform_admin`
- **THEN** the request is rejected with `403 permission_denied` and no state changes

#### Scenario: Missing signed request rejected
- **WHEN** a write arrives with a valid session cookie but no valid signed request
- **THEN** the request is rejected and no state changes
