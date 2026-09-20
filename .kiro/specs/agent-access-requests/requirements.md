# Requirements Document

## Introduction

Agent Access Requests lets autonomous AI agents ask a human operator for capabilities they do not yet have, and lets the operator approve, reject, or otherwise act on those asks from the Admin Console. Three request kinds are supported:

1. **Access request** — an agent asks for a permission grant on a credential/service that **already exists** in the tenant (possibly created by the operator or another agent).
2. **Integration proposal** — an agent proposes registering a **brand-new** service (OpenAPI spec, auth scheme, base URL, and non-secret config such as a client ID). The critical secret material (client secret, password, private-key passphrase) is deliberately left blank; the human operator fills it during the approval flow, may edit any proposed config, tests the connection, then finalizes the service registration. Applies to REST/API services and to SSH machines.
3. **Share request** — an agent asks to **share** a credential/service it can access with another agent, OR asks for access to a credential/service **created/owned by another agent**. This is distinct from an integration proposal: the target already exists; the request is about who may use it.

All three surface in a dedicated, clearly separated review area in the Admin Console where the operator Approves, Rejects (with a reason), or (for integration proposals) fills secrets / edits config / tests before finalizing. Requests carry a default 30-day expiration; an unactioned request expires. Every state change emits an audit event through the single admin-api chokepoint; the full flow is OpenTelemetry-instrumented; and a headless browser end-to-end test proves the operator review screen exists and works.

This feature is **additive and backwards compatible**: it introduces new domain tables, new REST paths, and new MCP tools; it changes no existing wire surface and requires no change to existing tests. On approval it reuses the existing permission-grant, service-registration, credential-storage, and audit machinery rather than replacing it.

## Glossary

- **Access_Request**: An agent's ask for a permission grant `(service, action)` on an existing service/credential in its tenant. Prefixed ULID `request_…`; discriminated by `kind = access`.
- **Integration_Proposal**: An agent's ask to register a new service, carrying OpenAPI reference, `auth_scheme`, base URL(s), and non-secret config, with secret fields blank. Prefixed ULID `request_…`; `kind = integration`.
- **Share_Request**: An agent's ask to grant another agent access to an existing service/credential, or an agent's ask for access to a service/credential owned by another agent. Prefixed ULID `request_…`; `kind = share`.
- **Access_Request_Record**: Any of the three above; the umbrella row in the `access_requests` table. "Request" in this document refers to an Access_Request_Record unless qualified.
- **Requesting_Agent**: The agent that created the request. Resolved from the Agent API Key auth context (MCP), never from a tool parameter.
- **Target_Agent**: For a Share_Request, the agent that would receive access.
- **Operator**: A human authenticated via Keycloak (ADR-0020) who reviews requests in the Admin Console.
- **Admin_API**: The FastAPI Admin REST API (`apps/admin-api/`); the audit chokepoint (P-2, ADR-0014.7) and the admin-ui's only upstream (ADR-0019).
- **MCP_Server**: The Anthropic-SDK Python MCP server (`apps/mcp-server/`) that exposes the agent-facing request tools.
- **Admin_Console**: The AdminJS 7.x BFF operator UI (`apps/admin-ui/`); holds no DB connection (ADR-0019).
- **Requests_Review_Area**: The dedicated, separated section of the Admin_Console listing pending requests with Approve / Reject / (for integrations) Edit-and-Test controls.
- **Vault_Adapter**: The Go service that stores/retrieves encrypted credentials; the only component that ever holds operator-supplied secret material (P-1).
- **Request_Status**: One of `pending`, `approved`, `rejected`, `expired`, `cancelled`.
- **Default_Request_TTL**: The default lifetime of a pending request before it expires — 30 days, expressed as an `expires_at` RFC 3339 UTC timestamp.
- **Signed_Request**: The Ed25519 `AdminUiSignedRequest` JWT that, together with the `mintkey_session` cookie, authenticates admin-ui state-changing calls to admin-api (ADR-0019).
- **Change_Channel**: Postgres `LISTEN/NOTIFY` global channels with application-layer tenant filtering (ADR-0010, ADR-0014.1).
- **Connection_Test**: An operator-triggered check that a proposed/edited integration's credential and base URL produce a successful upstream handshake, performed without exposing the secret to the operator or agent.

## Requirements

### Requirement 1: Agent Requests Access to an Existing Service (Access_Request)

**User Story:** As an autonomous agent, I want to request a permission grant on a service that already exists in my tenant, so that an operator can grant me access without me holding the credential.

#### Acceptance Criteria

1. WHEN the Requesting_Agent calls the MCP tool `request_access` with a `service_id` and an `action`, THE MCP_Server SHALL create an Access_Request with `kind = access`, `status = pending`, the Requesting_Agent resolved from auth context, and an `expires_at` set to the Default_Request_TTL.
2. WHEN an Access_Request is created, THE Admin_API SHALL persist it in the `access_requests` table with the caller's `tenant_id` and return a `request_id` with the `request_` prefix.
3. IF `service_id` or `action` is omitted or empty, THEN THE Admin_API SHALL reject the request with error code `invalid_argument`, SHALL indicate the missing field, and SHALL NOT create a request row.
4. IF the referenced `service_id` does not exist in the Requesting_Agent's tenant, THEN THE Admin_API SHALL reject the request with error code `service_not_found` and SHALL NOT create a request row.
5. IF the Requesting_Agent already holds a permission grant for the exact `(service_id, action)`, THEN THE Admin_API SHALL reject the request with error code `already_granted` and SHALL NOT create a request row.
6. IF an identical pending Access_Request from the same Requesting_Agent for the same `(service_id, action)` already exists, THEN THE Admin_API SHALL reject the duplicate with error code `request_already_pending` and SHALL NOT create a second request row.
7. WHEN the Requesting_Agent calls the MCP tool `list_my_requests`, THE MCP_Server SHALL return that agent's requests filtered to its tenant, including `request_id`, `kind`, `status`, `created_at`, and `expires_at`.

### Requirement 2: Agent Proposes a New Integration (Integration_Proposal)

**User Story:** As an autonomous agent, I want to propose registering a new backend service with its OpenAPI spec, auth model, base URL, and non-secret config, so that an operator can review, supply the secret, test, and finalize it.

#### Acceptance Criteria

1. WHEN the Requesting_Agent calls the MCP tool `propose_integration` with a non-empty service `name`, a non-empty `base_url`, an `auth_scheme`, an optional `openapi_url`, and a non-secret `config` object, THE MCP_Server SHALL create an Integration_Proposal with `kind = integration`, `status = pending`, and `expires_at` set to the Default_Request_TTL.
2. IF the call to `propose_integration` omits or supplies an empty value for any of `name`, `base_url`, or `auth_scheme`, THEN THE Admin_API SHALL reject the proposal with error code `invalid_argument`, SHALL indicate which required field is missing, and SHALL NOT create an Integration_Proposal.
3. IF the supplied `auth_scheme` is not a member of the closed `auth_scheme` enum defined in `docs/architecture/contracts/mcp/tools.yaml`, THEN THE Admin_API SHALL reject the proposal with error code `invalid_argument` and SHALL NOT create an Integration_Proposal.
4. IF the proposal `config` object contains any field whose name matches the secret denylist (`*_secret`, `*_password`, `*_passphrase`, `private_key`, `token`, `api_key`), THEN THE Admin_API SHALL reject the proposal with error code `secret_field_not_allowed`, SHALL indicate the offending field name, and SHALL NOT create an Integration_Proposal; otherwise THE Admin_API SHALL accept non-secret fields (for example `client_id`, `token_url`, `ssh_user`, `header_name`).
5. WHERE the proposed `auth_scheme` is an SSH scheme, THE Admin_API SHALL require `base_url` in `ssh://host:port` form per ADR-0023.
6. WHERE the proposed `auth_scheme` is an SSH scheme, IF the proposal includes a `target_address` field, THEN THE Admin_API SHALL reject the proposal with error code `invalid_argument` and SHALL NOT create an Integration_Proposal.
7. WHEN an Integration_Proposal is stored, THE Admin_API SHALL persist the proposed non-secret config as structured data on the request row and SHALL NOT create a `services` row until the proposal is approved.
8. WHEN the Requesting_Agent supplies an `openapi_url`, THE Admin_API SHALL validate that the URL uses the HTTPS scheme and passes the existing SSRF allowlist check before storing it.
9. IF a supplied `openapi_url` is not HTTPS or fails the SSRF allowlist check, THEN THE Admin_API SHALL reject the proposal with error code `invalid_argument`, SHALL indicate that the OpenAPI URL was rejected, and SHALL NOT create an Integration_Proposal.

### Requirement 3: Agent-to-Agent Sharing Requests (Share_Request)

**User Story:** As an autonomous agent, I want to request sharing a credential/service I can access with another agent, or request access to one owned by another agent, so that access can be extended without duplicating credentials.

#### Acceptance Criteria

1. WHEN the Requesting_Agent calls the MCP tool `request_share` with a non-empty `service_id`, a non-empty `action`, and a non-empty `target_agent_id`, THE MCP_Server SHALL create a Share_Request with `kind = share`, `status = pending`, and `expires_at` set to the Default_Request_TTL.
2. WHEN a Share_Request is created, THE Admin_API SHALL record whether it is an outbound share (Requesting_Agent shares access it holds with a Target_Agent) or an inbound access ask (Requesting_Agent asks for access owned by another agent), exposing this distinction as a `share_direction` field with values `outbound` or `inbound`.
3. IF `service_id`, `action`, or `target_agent_id` is omitted or empty, THEN THE Admin_API SHALL reject the request with error code `invalid_argument`, SHALL indicate the missing field, and SHALL NOT create a request row.
4. IF the `target_agent_id` equals the Requesting_Agent's own id, THEN THE Admin_API SHALL reject the request with error code `invalid_argument` and SHALL NOT create a request row.
5. IF the referenced `service_id` does not exist in the Requesting_Agent's tenant, THEN THE Admin_API SHALL reject the request with error code `service_not_found` and SHALL NOT create a request row.
6. IF the `target_agent_id` does not exist in the Requesting_Agent's tenant, THEN THE Admin_API SHALL reject the request with error code `agent_not_found` and SHALL NOT create a request row.
7. WHERE `share_direction` is `outbound`, IF the Requesting_Agent does not currently hold a permission grant for the `(service_id, action)` being shared, THEN THE Admin_API SHALL reject the request with error code `action_not_granted` and SHALL NOT create a request row.
8. IF the Target_Agent already holds a permission grant for the exact `(service_id, action)`, THEN THE Admin_API SHALL reject the Share_Request with error code `already_granted` and SHALL NOT create a request row.
9. THE Admin_API SHALL treat a Share_Request as distinct from an Integration_Proposal such that a Share_Request SHALL reference an existing `service_id` and SHALL NOT carry a proposed-config payload.

### Requirement 4: Operator Reviews Pending Requests

**User Story:** As an operator, I want a dedicated area that lists all pending agent requests, so that I can see what agents are asking for and act on each.

#### Acceptance Criteria

1. WHEN an authenticated Operator calls `GET /v1/tenants/{tenant_id}/access-requests`, THE Admin_API SHALL return the tenant's requests filtered by RLS, supporting optional filtering by `status` and by `kind`, ordered by `created_at` descending.
2. THE Admin_API SHALL include for each request: `request_id`, `kind`, `status`, `requesting_agent_id`, the target reference (`service_id`, `action`, `target_agent_id`, or proposed-config summary as applicable), `created_at`, and `expires_at`.
3. IF a supplied `status` or `kind` filter value is not a member of its respective enum, THEN THE Admin_API SHALL reject the call with error code `invalid_argument` and SHALL indicate the offending filter.
4. IF the referenced `request_id` does not exist in the Operator's tenant, THEN THE Admin_API SHALL respond with error code `request_not_found` and SHALL NOT reveal cross-tenant existence.
5. WHEN an Operator opens the Requests_Review_Area in the Admin_Console, THE Admin_Console SHALL display pending requests as a section clearly separated from the existing services, agents, and permissions resources.
6. WHEN an Operator selects a request in the Requests_Review_Area, THE Admin_Console SHALL display the full request detail, including the requesting agent, what is being asked, and — for an Integration_Proposal — the proposed non-secret config with the secret fields shown as empty and clearly labelled as operator-supplied.
7. THE Admin_Console SHALL fetch and mutate requests exclusively through the Admin_API BFF routes and SHALL hold no direct database connection (ADR-0019).

### Requirement 5: Operator Approves an Access_Request

**User Story:** As an operator, I want to approve an access request with one action, so that the requesting agent immediately gains the permission grant.

#### Acceptance Criteria

1. WHEN an Operator approves an Access_Request whose `status` is `pending` via `POST /v1/tenants/{tenant_id}/access-requests/{request_id}/approve`, THE Admin_API SHALL create the corresponding permission grant `(agent, service, action)` using the existing grant machinery and SHALL set the request `status` to `approved`.
2. IF the approve call is missing the `mintkey_session` cookie or a valid Signed_Request, or their claims disagree (`sub != operator_id` or `tnt != tenant_id`) per ADR-0019, THEN THE Admin_API SHALL reject the call as unauthorized, SHALL NOT create a grant, and SHALL leave the request `status` unchanged.
3. WHEN an approve call is authorized, THE Admin_API SHALL derive the effective identity from the validated session, not from the Signed_Request JWT body (ADR-0019).
4. WHEN a permission grant is created by approval, THE Admin_API SHALL emit the existing `agent.permission.granted` audit event in addition to the request state-change audit event.
5. IF the referenced `request_id` does not exist in the Operator's tenant, THEN THE Admin_API SHALL respond with error code `request_not_found` and SHALL NOT create a grant.
6. IF the request is not in `status = pending`, THEN THE Admin_API SHALL reject the approve call with error code `request_not_pending`, SHALL NOT create a grant, and SHALL leave the request `status` unchanged.
7. WHEN an Access_Request is approved, THE Admin_API SHALL publish the resulting grant change on the appropriate Change_Channel so that dependent components observe it within 5 seconds (P-9).

### Requirement 6: Operator Fills Secret, Edits Config, Tests, and Finalizes an Integration_Proposal

**User Story:** As an operator, I want to fill the missing secret, optionally edit the proposed config, test the connection, and then finalize an integration proposal, so that a new service is registered correctly without the agent ever seeing the secret.

#### Acceptance Criteria

1. WHEN an Operator submits secret material for an Integration_Proposal, THE Admin_API SHALL send the secret to the Vault_Adapter only and SHALL NOT persist it on the request row, in any log, in any audit payload, or in any OTel span attribute (P-1, S-SEC-1, ADR-0017.6).
2. WHERE an Operator edits the proposed non-secret config before finalizing, THE Admin_API SHALL apply the operator's edited values in place of the agent-proposed values.
3. WHEN an Operator triggers a Connection_Test via `POST /v1/tenants/{tenant_id}/access-requests/{request_id}/test`, THE Admin_API SHALL perform an upstream handshake using the operator-supplied secret and the (possibly edited) config with a handshake timeout of 10 seconds, and SHALL return a pass/fail result and a diagnostic message that contains no secret material.
4. IF a Connection_Test upstream handshake does not complete within the 10-second timeout, THEN THE Admin_API SHALL return a fail result with a diagnostic message indicating a connection timeout that contains no secret material.
5. WHEN an Operator finalizes an approved-and-tested Integration_Proposal via the approve endpoint, THE Admin_API SHALL create the `services` row and store the credential in the Vault_Adapter using the existing service-registration and credential machinery, emit the existing `service.registered` and `credential.registered` audit events, and set the request `status` to `approved`.
6. IF an Operator attempts to finalize an Integration_Proposal whose required secret fields are still blank, THEN THE Admin_API SHALL reject finalization with error code `missing_secret_material` and SHALL NOT create the service.
7. IF the Vault_Adapter is unavailable when an Operator submits secret material or finalizes an Integration_Proposal, THEN THE Admin_API SHALL reject the operation with an error indicating the credential store is unavailable, SHALL NOT create the service, and SHALL NOT persist the secret on the request row, in any log, in any audit payload, or in any OTel span attribute (P-1, S-SEC-1).
8. THE Admin_Console SHALL present, on an Integration_Proposal detail, inputs for the missing secret fields, editable non-secret config fields, a "Test connection" control that displays the Connection_Test result, and a "Finalize" control that is enabled only after the required secrets are supplied.

### Requirement 7: Operator Approves a Share_Request

**User Story:** As an operator, I want to approve a share request, so that the target agent gains access to the existing service/credential.

#### Acceptance Criteria

1. WHEN an Operator approves a Share_Request whose `status` is `pending`, THE Admin_API SHALL create the permission grant `(target_agent, service, action)` using the existing grant machinery and SHALL set the request `status` to `approved`.
2. WHEN a Share_Request is approved, THE Admin_API SHALL emit the `agent.permission.granted` audit event and a request state-change audit event, and SHALL publish the grant change on the Change_Channel so dependent components observe it within 5 seconds (P-9).
3. IF the referenced `service_id` no longer exists at approval time, THEN THE Admin_API SHALL reject the approval with error code `service_not_found` and SHALL leave the request `status` unchanged.
4. IF an Operator attempts to approve a Share_Request whose `status` is not `pending`, THEN THE Admin_API SHALL reject the approval with error code `request_not_pending` and SHALL leave the request `status` unchanged.
5. IF the permission grant `(target_agent, service, action)` already exists at approval time, THEN THE Admin_API SHALL set the request `status` to `approved` without creating a duplicate grant and SHALL emit the request state-change audit event.
6. WHEN a share grant is later revoked by an Operator, THE Admin_API SHALL emit the `agent.permission.revoked` audit event and publish the revocation on the Change_Channel within 5 seconds (P-9).

### Requirement 8: Operator Rejects a Request with a Reason

**User Story:** As an operator, I want to reject a request and record why, so that the decision is auditable and the agent can be informed.

#### Acceptance Criteria

1. WHEN an Operator rejects a request whose `status` is `pending` via `POST /v1/tenants/{tenant_id}/access-requests/{request_id}/reject` with a non-empty `reason`, THE Admin_API SHALL set the request `status` to `rejected` and SHALL store the `reason` on the request row.
2. IF a reject call omits the `reason`, supplies an empty or whitespace-only `reason`, or supplies a `reason` longer than 1000 characters, THEN THE Admin_API SHALL reject the call with error code `reason_required` and SHALL leave the request `status` unchanged.
3. WHEN a request is rejected, THE Admin_API SHALL NOT create any permission grant, service, or credential.
4. WHEN a request is rejected, THE Requesting_Agent's subsequent call to `list_my_requests` SHALL show that request with `status = rejected`.
5. WHEN an Operator submits a reject action in the Requests_Review_Area without entering a reason, THE Admin_Console SHALL block submission and SHALL prompt the Operator to enter a reason.
6. IF the referenced `request_id` does not exist in the Operator's tenant, THEN THE Admin_API SHALL respond with error code `request_not_found` and SHALL NOT change any request.
7. IF an Operator attempts to reject a request whose `status` is not `pending`, THEN THE Admin_API SHALL reject the call with error code `request_not_pending` and SHALL leave the existing `status` and `reason` unchanged.

### Requirement 9: Default 30-Day Expiration

**User Story:** As an operator, I want pending requests to expire automatically after a default period, so that stale asks do not accumulate.

#### Acceptance Criteria

1. WHEN a request is created, THE Admin_API SHALL set `expires_at` to the creation time plus the Default_Request_TTL of 30 days, expressed as an RFC 3339 UTC timestamp.
2. WHEN a request with `status = pending` is evaluated at a time greater than or equal to its `expires_at` timestamp, THE Admin_API SHALL set its `status` to `expired`.
3. WHILE a request has `status = pending` and the current time is strictly earlier than its `expires_at` timestamp, THE Admin_API SHALL retain its `status` as `pending`.
4. WHEN a request transitions to `expired`, THE Admin_API SHALL NOT create any permission grant, service, or credential.
5. IF an Operator attempts to approve or reject a request whose `status` is `expired`, THEN THE Admin_API SHALL reject the action with error code `request_not_pending` and SHALL retain the request `status` as `expired`.
6. THE Default_Request_TTL SHALL be a single documented default value (30 days); per-tenant or per-kind configurability is out of scope for this feature and is recorded as an open refinement.

### Requirement 10: Auditing of Every State Change

**User Story:** As a security-conscious operator, I want every request state change audited through the single chokepoint, so that the request lifecycle is tamper-evident and complete.

#### Acceptance Criteria

1. WHEN any request state change occurs — created, approved, rejected, expired, secret filled, service finalized, share grant granted, share grant revoked — THE Admin_API SHALL emit an audit event via the single `audit.emit()` chokepoint (P-2, ADR-0014.7).
2. THE Admin_API SHALL define the new audit event types in `docs/architecture/contracts/events/audit-event.schema.json` with a new `target_type` value for access requests and an envelope conformant to the existing per-tenant hash chain (`prev_hash` + `hash`).
3. THE Admin_API SHALL NOT include any secret material — client secret, password, private-key passphrase, or any denylisted field value — in any audit payload for these events.
4. WHEN an approval creates a grant, service, or credential, THE Admin_API SHALL emit both the request state-change audit event and the corresponding existing audit event (`agent.permission.granted`, `service.registered`, `credential.registered`) within the same audited operation.
5. THE Admin_API SHALL record the acting `actor_id` and `actor_type` (`agent` for agent-initiated creation, `operator` for operator actions, `system` for expiration) on each emitted audit event, deriving operator identity from the validated session (ADR-0019).
6. IF the audit event for a request state change cannot be emitted, THEN THE Admin_API SHALL abort the state change so that no grant, service, credential, or request status update is persisted without its corresponding audit event (P-2).

### Requirement 11: OpenTelemetry Coverage

**User Story:** As an operator, I want the full request-to-approval flow traced and measured, so that I can observe and debug it end to end without leaking secrets.

#### Acceptance Criteria

1. WHEN an agent request flows from MCP_Server through Admin_API to the Admin_Console approval, THE system SHALL produce OTel spans for the MCP call, the admin-api handling, and the operator approval that share a single trace ID, such that the spans are retrievable as one trace.
2. WHEN a request transitions to the created, approved, rejected, or expired state, THE system SHALL increment the corresponding OTel counter metric labelled with `kind` and `tenant_id`.
3. THE system SHALL restrict OTel span attributes to the allowlist and SHALL NOT place any value matching `*_token`, `*_secret`, `*_password`, `*_passphrase`, `Authorization`, or `Cookie` on any span (P-7, ADR-0017.6).
4. WHEN a request undergoes a state transition, THE system SHALL emit a structured JSON log entry containing the `request_id`, `kind`, and resulting `status`.
5. IF a log entry or span attribute would contain secret material matching `*_token`, `*_secret`, `*_password`, `*_passphrase`, `Authorization`, or `Cookie`, THEN THE system SHALL omit that value so that no secret material appears in the emitted log or span (P-7, ADR-0017.6).

### Requirement 12: Multi-Tenancy and Row-Level Security

**User Story:** As an operator, I want request data isolated per tenant, so that no agent or operator can see or act on another tenant's requests.

#### Acceptance Criteria

1. THE `access_requests` table (and any related table introduced by this feature) SHALL carry a `tenant_id UUID NOT NULL` column and a Postgres RLS `tenant_isolation` policy created in the same Liquibase changeset (P-3, ADR-0008, ADR-0015).
2. WHEN the Admin_API or MCP_Server begins a database transaction on behalf of an authenticated caller, THE service SHALL set `app.current_tenant` (transaction-scoped) to the caller's tenant so that RLS scopes all request rows to that tenant.
3. IF a request `request_id` from a different tenant is referenced on a read or a mutation, THEN THE Admin_API SHALL respond as though the request does not exist (error code `request_not_found`) rather than revealing cross-tenant existence.
4. IF the tenant context cannot be resolved for a request-touching operation, THEN THE service SHALL reject the operation rather than execute it without a tenant scope.
5. THE schema for all new tables SHALL be defined in new Liquibase changesets under `apps/admin-api/db/changelog/`, and SHALL NOT be defined by adding columns in SQLAlchemy (P-8, ADR-0015).
6. WHEN new tables are added, THE SQLAlchemy `Mapped` models SHALL mirror the introspected Liquibase schema and SHALL pass the existing CI schema-diff check.

### Requirement 13: Contract-First Wire Surfaces

**User Story:** As a developer, I want the new endpoints, tools, and events defined in the canonical contracts before implementation, so that the running services conform to checked-in specs.

#### Acceptance Criteria

1. WHERE new REST endpoints are introduced by this feature, THE `docs/architecture/contracts/rest/openapi.yaml` file SHALL define each endpoint in OAS 3.1 form, expressing every nullable field as `type: [<T>, "null"]` and containing zero occurrences of the OAS 3.0 `nullable: true` form on those fields (P-4, ADR-0017).
2. WHERE new MCP tools are introduced by this feature, THE `docs/architecture/contracts/mcp/tools.yaml` file SHALL define each of `request_access`, `propose_integration`, `request_share`, and `list_my_requests`, and each such tool definition SHALL declare no `tenant_id` argument in its input schema (tenant resolved from auth context, ADR-0009).
3. WHERE new error conditions are introduced by this feature, THE new error codes SHALL be added to the closed `mintkey:code` enum in `openapi.yaml` and to the corresponding error-code enum in `tools.yaml`, such that every error code returned by the feature's endpoints and tools is a member of both enums (ADR-0017.10).
4. THE new wire IDs SHALL use prefixed ULIDs (`request_` for access-request rows; `share_` where a distinct share-grant row is introduced) matching the pattern `^<prefix>_[0-9A-HJKMNP-TV-Z]{26}$`, and SHALL contain no bare UUIDs on any wire surface (ADR-0017.11).
5. WHEN the Admin_API emits its OpenAPI document, THE emitted document SHALL be structurally equivalent to the checked-in `docs/architecture/contracts/rest/openapi.yaml` such that the CI contract round-trip diff reports no differences (P-4).
6. IF the CI contract round-trip diff reports any difference between the Admin_API-emitted OpenAPI document and the checked-in `openapi.yaml`, THEN THE CI build SHALL fail with an indication identifying the drift (P-4).

### Requirement 14: Backwards Compatibility and Test Isolation

**User Story:** As a maintainer, I want this feature to add capability without altering existing behavior or existing tests, so that nothing already shipped regresses.

#### Acceptance Criteria

1. THE feature SHALL add new tables, endpoints, MCP tools, and audit event types without changing the request schema, response schema, or observable behavior of any existing endpoint, MCP tool, table, or audit event type.
2. THE feature SHALL add new test files only, and SHALL NOT modify, rename, or delete any existing test.
3. WHEN the existing test suite is run after this feature is merged, THE existing tests SHALL produce the same pass results as before, with zero new failures and zero previously-running tests skipped.
4. WHERE approval reuses existing grant, service-registration, or credential machinery, THE feature SHALL call that machinery through its existing interfaces without changing their signatures, semantics, or return contracts.
5. IF delivering this feature would require changing an existing wire surface, schema, or test, THEN the change SHALL be surfaced as a blocking issue for the maintainer rather than applied silently.

### Requirement 15: Headless Admin UI End-to-End Test (Mandatory, Reviewable Evidence)

**User Story:** As a maintainer who was previously burned by features claimed done without visible UI proof, I want an automated headless browser test that exercises the operator review screen, so that there is clear, easy-to-review evidence the interaction screen actually exists and works.

#### Acceptance Criteria

1. THE feature SHALL include a headless browser UI automation test (Playwright, aligned with the existing `.github/workflows/playwright.yml`) that runs against the Admin_Console.
2. WHEN the end-to-end test runs, THE test SHALL log into the Mintkey Admin_Console and navigate to the Requests_Review_Area.
3. IF login to the Admin_Console does not reach the Requests_Review_Area within 30 seconds, THEN the test SHALL fail with an error indicating the login or navigation step did not complete.
4. WHEN the Requests_Review_Area is displayed, THE test SHALL assert that a UI element identifying the pre-seeded pending agent request (by its request identifier) is rendered and that its displayed status is "pending".
5. WHEN the test exercises the Approve path on the visible request, THE test SHALL assert that the request's displayed status in the UI changes to "approved".
6. WHEN the test exercises the Reject-with-reason path on the visible request in a separate test case, THE test SHALL submit a non-empty rejection reason and SHALL assert that the request's displayed status in the UI changes to "rejected" and that the submitted reason is displayed.
7. THE test SHALL capture a screenshot artifact AND a Playwright trace artifact at two points: (a) when the pending request is first visible, and (b) after the operator action completes and the resulting status is displayed.
8. THE captured screenshot and trace artifacts SHALL be uploaded as retained CI artifacts per the Playwright workflow such that a reviewer can retrieve and open them after the run completes.
9. THE end-to-end test SHALL be a new test added under the repository's UI test location and SHALL NOT modify any existing test (per Requirement 14).
10. IF the Requests_Review_Area or its Approve or Reject controls are absent or non-functional, THEN the end-to-end test SHALL fail.
