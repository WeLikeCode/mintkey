# Design: admin-ui-agent-governance

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- Every resource is a `RestResource` (`UI/lib/rest-resource.ts`): `find` forwards only the keys of its `filterKeys` as query
  parameters and reads the list under `listKey`; `recordTransform` runs on every record. The permissions resource has
  `filterKeys: ["q", "service_id"]` although `agent_id` is a filter property, so an agent filter is not forwarded today.
- Writes go through `apiWrite` with `operatorOptsFromAdmin(currentAdmin)` and `tenantIdFromAdmin(currentAdmin)`; reads of a
  BFF action use `currentAdmin.sessionToken` as the `mintkey_session` cookie and add `X-Platform-Admin: true` for a platform
  admin (`RestResource._sessionHeaders`, `crossTenantServicesList`).
- `getCredentialStatus` (`apps/admin-ui/src/lib/credential-status.ts`, on the base) turns `auth_scheme` and
  `current_key_version` into a label (`auth_scheme` `none` gives `n/a (no auth)`); the operator list
  `GET /v1/tenants/{tenant_id}/permissions` already takes `agent_id` (a UUID or `agent_` id) today, and
  `grant-expiry` adds `grantor_agent_id`; admin-api
  reads `current_key_version` as the maximum version of the active credentials, so a cleared credential reads 0.
- `ConfirmAction` posts an empty body; existing tests read `services.ts` and `agents.ts` as text and `index.ts` for wiring.
- `UI/resources/audit.ts` lists event types, actor types and target types as `availableValues`.
- The vitest workspace has a node project (`tests/**/*.test.ts`) and a jsdom project (`tests/**/*.render.test.tsx`); the L4
  gate runs both with `--testTimeout=30000`; Playwright is not in the gate.

## Relied on (given by the named change; not redefined here)

- `grant-expiry`: every grant object of `GET /v1/tenants/{tenant_id}/permissions` carries `expires_at`, `expired`,
  `grantor_type` (`operator` | `agent`) and `grantor_id` (an `agent_` id for an agent grantor); the list accepts
  `grantor_agent_id` and, already today, `agent_id`.
- `agent-roles-and-ownership`: agent objects carry `role`; `GET .../agents?role=`; `PATCH .../agents/{agent_id}` takes exactly
  `{"role": ...}`; service objects carry `owner_agent_id` and `created_by_agent_id` (`agent_...` or null);
  `GET .../services?owner_agent_id=` takes an agent id or `operators`; `POST .../services/{service_id}/transfer` takes
  `{"to_agent_id": "agent_..." | null}` and answers 422 `invalid_transfer_target` (`reason` `agent_not_publisher` or
  `agent_not_active`) or 404 `not_found`.
- `agent-access-requests`: the operator API `GET .../access-requests` (filters `status`, `service_id`, `requester_agent_id`,
  `owner_agent_id`; answers `{"access_requests": [...]}`), `GET .../{request_id}`, `POST .../{request_id}/approve`
  (`{ttl_seconds?, note?}`; answers the request and `grant: {id, action, expires_at}`) and `POST .../{request_id}/deny`
  (`{note?}`), the request object keys (`id`, `service_slug`, `requester_agent_id`, `requester_agent_name`, `actions`,
  `reason`, `requested_ttl_seconds`, `status`, `decided_by_type`, `decided_by_id`, `decided_at`, `decision_note`, `grant_id`,
  `created_at`, `pending_until`) and the error codes `request_not_pending`, `grant_conflict`, `requester_not_active`,
  `already_granted`.
- The audit event names come from `agent-roles-and-ownership` (`agent.role.changed`, `service.ownership_transferred`),
  `agent-principal-and-egress` (`agent.operation.denied`), `agent-service-routes` (`service.credential.set`,
  `service.credential.cleared`) and
  `agent-access-requests` (`access_request.created`, `.approved`, `.denied`, `.cancelled`, `.expired`; target type
  `access_request`; actor type `system` for `.expired`).

## Decisions

**D1. Everything decidable lives in pure functions** (`src/lib/agent-governance.ts`): labels, the expiry badge, the
transfer and approval bodies, the error messages. Resources call them from `recordTransform` and handlers; components only
render what they are given. A scenario is a function call, a handler call with a mocked `fetch`, a resource option, or one
render test.

**D2. The expired badge follows the API.** `expired` is the server's decision at read time; the UI never compares
`expires_at` with the browser's clock. Without `expired` and with an `expires_at` the badge reads "Expires <date>".

**D3. Dedicated actions, exact bodies.** The role actions send `{"role": "publisher"}` or `{"role": "consumer"}` and nothing
else; the transfer sends exactly `{"to_agent_id": <id or null>}`. The `edit` action of agents stays without `role`.

**D4. Operator-only by construction.** Every call is a tenant-session call through `apiWrite` or a session-cookie read; no
action sends an agent key, and a role or ownership change is possible only here and through the operator API.

**D5. Added: one panel, one BFF read.** The agent show page calls the record action `governanceSummary`, which makes five
reads (owned services, grants received, grants given, requests made, pending requests for its services) and returns
`{owned_services, grants_received, grants_given, requests_made, requests_incoming, errors}`. A failed read gives an empty
section and a line in `errors`; the others still show.

**D6. Added: a generic input form.** `PayloadActionForm` renders the fields named in `action.custom.fields` and posts their
raw string values with `recordAction`; the handler validates and answers a notice. The transfer, approve and deny actions
use it; `ConfirmAction` keeps serving the actions without input.

**D7. Added: the new owner is typed.** The transfer form takes an agent id (empty or `operators` makes the service
operator-owned); admin-api checks that it is an active publisher and the form shows its reason in words
(`governanceErrorMessage`). A picker is a follow-up.

**D8. Added: access request actions only while pending.** `approveRequest` and `denyRequest` are visible when
`params.status` is `pending`; a decision that races with another one shows the server's `request_not_pending` as a notice.

**D9. Platform admins as today.** The summary read adds `X-Platform-Admin: true` for a platform admin and uses the session's
tenant like `RestResource`; nothing else about tenants changes.

## Interfaces

Given to nobody outside the UI. Inside it: `src/lib/agent-governance.ts` and `src/lib/governance-bff.ts` (signatures in the
spec), the resource `AccessRequestsResource` (`id` `access_requests`) and the components `PayloadActionForm`,
`AgentGovernancePanel` and `GrantExpiryBadge` registered in `src/components/index.ts`.

## Failure cases

- A failed read of one panel section: the section is empty and the panel lists the error; a failed write: an error notice with
  the server's reason in words (or its `title`, or a fixed fallback), nothing else changes.
- A record without a field (an older admin-api): the labels fall back (`consumer`, `operators`, "No expiry", "—").
- A platform admin whose session has no tenant: `tenantIdFromAdmin` throws, as for the other resources.

## Relation to the other changes

Merges after `agent-access-requests`, `agent-service-routes`, `agent-principal-and-egress`, `agent-roles-and-ownership` and
`grant-expiry`. It changes no admin-api route; the
audit filter lists are the UI's own copy of the contract's event names.

## Open questions

1. Should the operator's grant form accept an expiry? Recommendation: yes, in a follow-up, now that the API takes it.
2. Should the transfer form offer a list of active publishers? Recommendation: yes, with the role filter of the agents list.
