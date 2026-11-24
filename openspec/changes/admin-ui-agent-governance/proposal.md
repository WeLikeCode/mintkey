# The admin UI shows who owns, grants and requests, and lets an operator steer it

## Why

Agents now have roles, own services, give each other time-boxed access and ask for it. An operator has to see all of it in one
place and act on it: which agents are publishers, who owns each service and whether it has a credential, which grants
exist, who gave them and when they end, which requests wait for a decision, and what the audit log recorded. Today the
admin UI shows agents, services and permissions without any of this, has no page for requests, and its audit filter does
not know the new event types.

## What Changes

- Agents: a `role` column and filter, two record actions that set the role (`Make publisher`, `Make consumer`), and a show-page
  panel with the services the agent owns, the grants it holds and has given, and the requests it made and received.
- Services: `owner` ("operators" or the agent id) and `credential` columns, an owner filter, and an operator-only `Transfer
  ownership` action (an agent id, or empty for operators).
- Permissions: grantor and expiry columns, an `Expired` badge (taken from the API's `expired`, never a browser clock), and
  filters for the grantee and the grantor agent.
- A new `Access requests` resource: list, show, filters, and `Approve` (a lifetime and a note) and `Deny` (a note) while a
  request is pending.
- The audit filter lists the new event types, the target type `access_request` and the actor type `system`.
- Pure helpers (`src/lib/agent-governance.ts`) decide every label, so the behaviour is tested without a browser; a generic
  form component renders the actions that take input.

## Capabilities

### New Capabilities
- `admin-ui-agent-governance`: the helpers, the server-side read and the components.
- `admin-ui-governance-views`: the Agents, Services, Permissions, Access requests and Audit Log resources' new columns, filters and actions.

## Impact

- Changed: `apps/admin-ui/src/resources/agents.ts`, `services.ts`, `permissions.ts`, `audit.ts`,
  `apps/admin-ui/src/index.ts`, `apps/admin-ui/src/components/index.ts`.
- New: `apps/admin-ui/src/lib/agent-governance.ts`, `apps/admin-ui/src/lib/governance-bff.ts`,
  `apps/admin-ui/src/resources/access-requests.ts`, `apps/admin-ui/src/components/actions/PayloadActionForm.tsx`,
  `apps/admin-ui/src/components/sections/AgentGovernancePanel.tsx`,
  `apps/admin-ui/src/components/properties/GrantExpiryBadge.tsx`; tests as listed per task in tasks.md.
- Existing tests that read `services.ts` and `agents.ts` as text (`tests/test_copyable_value.test.ts`,
  `tests/test_agent_secrets_resource.test.ts`, `tests/test_agent_created_notice.test.ts` and the service template tests) keep
  passing: the edits add to those files and do not rename what they match.
- Operators: nothing to configure. The panels and actions call the operator API of `grant-expiry`,
  `agent-roles-and-ownership` and `agent-access-requests` with the operator's session, as the other resources do.
- Out of scope: an expiry on the operator's grant form, a picker for the new owner (the form takes an id), constraints at
  approval, Playwright tests (`apps/admin-ui/e2e` is not run by the L4 gate), changes to admin-api.
- Depends on: `grant-expiry`, `agent-roles-and-ownership`, `agent-principal-and-egress` (the audit event name
  `agent.operation.denied`), `agent-service-routes` (`service.credential.set` and `service.credential.cleared`; both the audit
  filter lists and its test finds them in the contract) and `agent-access-requests`.
