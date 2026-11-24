# Admin UI governance views

## Purpose

What the Agents, Services, Permissions, Access requests and Audit Log resources of the admin UI show and let an operator do
about roles, ownership, grants and requests. Every write is an operator-session call to the operator API.

## ADDED Requirements

### Requirement: Agents show and filter the role
`apps/admin-ui/src/resources/agents.ts` SHALL declare the property `role` (string, `availableValues` `consumer` and
`publisher`), add `role` to `listProperties`, `showProperties` and `filterProperties` and to the resource's `filterKeys`, and
leave `editProperties` without it. The virtual show property `_governance` SHALL be in `showProperties` with
`Components.AgentGovernancePanel`.

#### Scenario: the role is a column, a filter and not editable
- **WHEN** `AgentsResource.options` and the resource's `find` are used with a filter `role` = `publisher` over a fetch mock
- **THEN** `listProperties`, `showProperties` and `filterProperties` contain `role`, `editProperties` does not, the property's
  values are `consumer` and `publisher`, `_governance` is in `showProperties`, and the requested URL contains `role=publisher`

### Requirement: An operator changes an agent's role
`AgentsResource` SHALL have the record actions `makePublisher` and `makeConsumer`, each with `Components.ConfirmAction` and a
`custom.description`, whose handlers on POST call `apiWrite` with `PATCH /v1/tenants/<tenantId>/agents/<recordId>` and the body
`{"role": "publisher"}` or `{"role": "consumer"}` and no other key. `makePublisher` SHALL be visible only for an agent whose
`params.status` is not `revoked` and whose role is not `publisher`; `makeConsumer` only for an agent whose role is
`publisher`. On a refusal the handler SHALL answer an error notice with `governanceErrorMessage(body, "Failed to change
role")`; on success a success notice whose message is exactly `Role set to publisher.` or `Role set to consumer.`

#### Scenario: promote and demote
- **WHEN** each handler runs on POST with the admin-api mock answering 200
- **THEN** `fetch` was called once with the URL ending `/v1/tenants/tenant_abc/agents/agent_X`, method `PATCH` and a JSON body
  equal to `{"role":"publisher"}` (then `{"role":"consumer"}`), the notice is `{type: "success", message: "Role set to publisher."}` (then `... consumer.`), and each action's `component` is
  `Components.ConfirmAction` with a non-empty `custom.description`

#### Scenario: visibility and refusal
- **WHEN** `isVisible` runs for roles `consumer`, `publisher` and a revoked consumer, for both actions; and a handler runs
  with the mock answering 404 `{"title": "Agent not found"}`
- **THEN** `makePublisher` is visible only for the active consumer, `makeConsumer` only for the publisher, and the refusal
  gives an error notice `Agent not found`

### Requirement: The agent page shows ownership, grants and requests
`AgentsResource` SHALL have the record action `governanceSummary` (`isVisible` false) whose handler calls
`fetchGovernanceSummary` with the session's tenant, the record id and `context.currentAdmin`, and answers `{record,
summary}`.

#### Scenario: the summary action
- **WHEN** the handler runs for `agent_X` as an operator and as a platform admin, over a fetch mock
- **THEN** the five URLs of `governanceUrls("tenant_abc", "agent_X")` were requested, with the cookie for the operator and
  with `X-Platform-Admin: true` too for the platform admin, and the answer holds `summary.owned_services`

### Requirement: Services show their owner and credential, and an operator transfers them
`apps/admin-ui/src/resources/services.ts` SHALL add the virtual properties `owner` and `credential` to `listProperties` and
`showProperties` (the latter staying on one line with `proxy_url`), the properties `owner_agent_id` and `created_by_agent_id`,
the filter `owner_agent_id` (in `filterKeys` and `filterProperties`, its description naming `operators`), and call
`decorateServiceRecord` in `recordTransform` after the `proxy_url` assignment. It SHALL have the record action
`transferOwnership` with `Components.PayloadActionForm` and `custom.fields` of one field `to_agent_id`, whose handler on POST
calls `apiWrite` with `POST /v1/tenants/<tenantId>/services/<recordId>/transfer` and exactly the body of
`transferBody(request.payload)`, and answers the success notice `Ownership transferred to <agent id>.` (or `Ownership transferred to operators.` for a null
target) or an error notice from `governanceErrorMessage(body, "Failed to transfer ownership")`. The action is visible for
every service record. The `owner` and `credential` virtual properties come from `decorateServiceRecord`.

#### Scenario: owner and credential columns
- **WHEN** `ServicesResource.adminResource.find` runs over a fetch mock listing an operator-owned service with
  `current_key_version` 0 and an agent-owned one with version 3
- **THEN** the records have `owner` `operators` and `agent_...`, `credential` `⚠ no credential` and `✓ configured v3`, and
  `proxy_url` is still set; `listProperties` and `showProperties` contain `owner` and `credential`, and a filter
  `owner_agent_id` = `operators` reaches the URL

#### Scenario: transfer to an agent and back to operators
- **WHEN** the `transferOwnership` handler runs with payloads `{to_agent_id: "agent_C"}` and `{to_agent_id: ""}`, the mock
  answering 200, and then with the mock answering 422 `{"mintkey:code": "invalid_transfer_target", "reason":
  "agent_not_publisher"}`
- **THEN** the bodies sent are exactly `{"to_agent_id":"agent_C"}` and `{"to_agent_id":null}` to the URL ending
  `/services/svc_X/transfer`, `isVisible` of the action is true for an `active` and for a `disabled` service record, the success notices are `Ownership transferred to agent_C.` and `Ownership transferred to
  operators.`, and the refusal gives the notice `The new owner must be an agent with the publisher role.`

### Requirement: Permissions show the grantor and the expiry
`apps/admin-ui/src/resources/permissions.ts` SHALL declare `expires_at`, `expired`, `grantor_type`, `grantor_id`, `grantor`,
`expiry` and `expiry_state`, show `expiry` and `grantor` in `listProperties` and `expires_at`, `expiry`, `grantor_type` and
`grantor` in `showProperties`, render `expiry` with `Components.GrantExpiryBadge`, forward `agent_id` and `grantor_agent_id`
as filters (`filterKeys`, `filterProperties`), and apply `decorateGrantRecord` after `normalisePermissionRecord` in
`recordTransform`.

#### Scenario: the expired badge and the grantor
- **WHEN** `PermissionsResource.adminResource.find` runs over a fetch mock listing a grant with `expired` true given by an
  agent, one with `expires_at` null given by an operator, and a grant whose agent id is a bare UUID
- **THEN** the records have `expiry_state` `expired`/`none`, `grantor` `agent_...`/`operator`, and the bare UUID is still
  normalised to the `agent_` form

#### Scenario: the filters reach admin-api
- **WHEN** `find` runs with filters `grantor_agent_id` = `agent_B` and `agent_id` = `agent_A`
- **THEN** the URL contains `grantor_agent_id=agent_B` and `agent_id=agent_A`

### Requirement: Access requests have their own resource
`apps/admin-ui/src/resources/access-requests.ts` SHALL export `AccessRequestsResource` (`resource` `access_requests`, a
`RestResource` on `/v1/tenants/{tenantId}/access-requests` with `getPath`, `listKey` `access_requests`, `filterKeys`
`status`, `service_id`, `requester_agent_id` and `owner_agent_id`, `recordTransform` `decorateAccessRequestRecord`), with
navigation name `Access requests`, `new`, `edit`, `delete` and `bulkDelete` hidden, the list columns `created_at`, `status`,
`service_slug`, `requester_agent_name`, `action`, `requested_ttl` and `pending_until`, a show page with the reason and the
decision fields, and `status` values `pending`, `approved`, `denied`, `cancelled` and `expired`. `apps/admin-ui/src/index.ts`
SHALL register it after the permissions resource.

#### Scenario: configuration and registration
- **WHEN** `AccessRequestsResource.options` is read and `src/index.ts` is read as text
- **THEN** the write actions are hidden, the list columns are as above, `showProperties` contains `reason`,
  `decided_by_type`, `decided_by_id`, `decided_at`, `decision_note` and `grant_id`, the status values are as above, the list of `resources` in `index.ts` has the
  `AccessRequestsResource` entry after the `PermissionsResource` entry, and a record from a fetch mock shows `action` `call`
  and `requested_ttl` `1 h`

### Requirement: An operator approves or denies a pending request
`AccessRequestsResource` SHALL have the record actions `approveRequest` and `denyRequest`, with `Components.PayloadActionForm`
(fields `ttl_seconds` and `note` for approve, `note` for deny), visible only when `params.status` is `pending`. Their handlers
on POST SHALL build the body with `decisionBody(request.payload, kind)` (an invalid value answers an error notice with its
`error` and no call), call `apiWrite` with `POST /v1/tenants/<tenantId>/access-requests/<recordId>/approve` or `/deny` and that
body, and answer a success notice (`Approved; access ends <grant.expires_at>.` for an approval, `Request denied.` for a denial) or an error notice from
`governanceErrorMessage(body, "Failed to decide the request")`.

#### Scenario: approve and deny
- **WHEN** `approveRequest` runs with `{ttl_seconds: "600", note: "ok"}` and the mock answering 200 with `grant.expires_at`;
  then `denyRequest` with `{note: "no"}`
- **THEN** the calls are `POST .../access-requests/areq_X/approve` with the body `{"ttl_seconds":600,"note":"ok"}` and `POST
  .../deny` with `{"note":"no"}`, the approval notice is `Approved; access ends <the mock's grant.expires_at>.` and the denial
  notice `Request denied.`

#### Scenario: bad input, refusals and visibility
- **WHEN** `approveRequest` runs with `{ttl_seconds: "59"}`; with the mock answering 409 `{"mintkey:code":
  "request_not_pending", "status": "approved"}`; and `isVisible` runs for statuses `pending` and `approved`
- **THEN** the first gives the lifetime error notice and no `fetch` call, the second the notice `This request is already
  approved.`, and the actions are visible for `pending` only

### Requirement: The audit filter knows the new events
`apps/admin-ui/src/resources/audit.ts` SHALL list in the `event_type` values `agent.role.changed`, `agent.operation.denied`,
`service.credential.set`, `service.credential.cleared`, `service.ownership_transferred`, `access_request.created`,
`access_request.approved`, `access_request.denied`, `access_request.cancelled` and `access_request.expired`; in the
`target_type` values `access_request`; and in the `actor_type` values `system`; each list without duplicates and with the
entries it had.

#### Scenario: the lists and the contract agree
- **WHEN** the three `availableValues` lists are read and `docs/architecture/contracts/events/audit-event.schema.json` is
  loaded
- **THEN** each new value is present exactly once, the old values are still present, and each of the ten event types is a key of
  the schema's `discriminator.mapping`
