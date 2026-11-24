# Tasks: admin-ui-agent-governance

Each task writes its tests first and sees them fail for the reason it names, then changes the code; a new module is
stubbed by the red step with the names and signatures of the spec (functions throw `new Error("not implemented")`, a
component renders `null`). Run the touched test files with `pnpm exec vitest run <file>` in `apps/admin-ui`, and
`pnpm exec tsc --noEmit` (it is in the L4 typecheck gate). No test needs a network, a browser or a clock.

Node tests follow `apps/admin-ui/tests/test_agents.test.ts`: `vi.mock("../src/lib/signed-request.js", ...)` with
`buildSignedRequest` resolving a fixed token, `vi.stubGlobal("fetch", mockFetch)`, and write handlers called as `handler(request,
response, context)` with `context.currentAdmin` `{operatorId: "op_123", tenantId: "tenant_abc"}` (no session token, so
`apiWrite` reaches the stubbed `fetch` directly, as in `test_agents.test.ts`; `signedFetch` is not mocked) and `context.record`
`{toJSON: () => ({params: {...}})}`. The summary read needs `sessionToken` in `currentAdmin`: its scenarios assert the cookie. Resource list tests call `<Resource>.adminResource.find(filter,
{}, context)` with the `makeFilter` shape of `apps/admin-ui/tests/unit/lib/rest-resource.test.ts`. Existing tests read
`apps/admin-ui/src/resources/services.ts` and `agents.ts` as text; each edit keeps the strings they match.

## 1. The helpers

- [ ] 1.1 Tests first, new file `apps/admin-ui/tests/test_agent_governance_lib.test.ts`, covering the five scenarios of "Pure
  helpers decide the labels and bodies"; red stubs `apps/admin-ui/src/lib/agent-governance.ts` with the exports and signatures
  of the spec (`AGENT_ROLE_VALUES` is already filled). Then fill it in; `credentialLabel` calls `getCredentialStatus` of
  `apps/admin-ui/src/lib/credential-status.ts` and does not copy its strings.

- [ ] 1.2 Tests first, new file `apps/admin-ui/tests/test_governance_bff.test.ts` (`vi.stubGlobal("fetch", ...)`), covering the
  two scenarios of "One server-side read gathers an agent's governance data"; red stubs
  `apps/admin-ui/src/lib/governance-bff.ts`. Then fill it in (the five requests run with `Promise.all`).

## 2. The components

- [ ] 2.1 Tests first, new file `apps/admin-ui/tests/GovernanceComponents.render.test.tsx` (jsdom project; `adminjs`
  and `@adminjs/design-system` are the stubs of `vitest.render.config.ts`; `recordAction` comes from
  `apps/admin-ui/tests/__mocks__/adminjs-stub.ts` as in `apps/admin-ui/tests/AgentSecretNewForm.render.test.tsx`), covering the
  the four render scenarios of "Generic components render the new views"; new file
  `apps/admin-ui/tests/test_governance_wiring.test.ts` reads `apps/admin-ui/src/components/index.ts` as text for the
  registration scenario. Red
  creates `apps/admin-ui/src/components/actions/PayloadActionForm.tsx`, `sections/AgentGovernancePanel.tsx` and
  `properties/GrantExpiryBadge.tsx` (default exports rendering null) and registers them in
  `apps/admin-ui/src/components/index.ts`. Then fill the components in, using the helpers of task 1.1 and the section
  layout of `apps/admin-ui/src/components/sections/TenantServicesPanel.tsx`.

## 3. The Agents resource

- [ ] 3.1 Tests first, new file `apps/admin-ui/tests/test_agents_governance.test.ts`, covering the scenario of "Agents show and
  filter the role", the two of "An operator changes an agent's role" and the one of "The agent page shows ownership, grants and
  requests". Then edit `apps/admin-ui/src/resources/agents.ts`: the `role` and `_governance` properties and lists, `"role"`
  in `filterKeys`, the actions `makePublisher`, `makeConsumer` and `governanceSummary`.

## 4. The Services resource

- [ ] 4.1 Tests first, new file `apps/admin-ui/tests/test_services_governance.test.ts`, covering the two scenarios of
  "Services show their owner and credential, and an operator transfers them". Then edit
  `apps/admin-ui/src/resources/services.ts`: the properties, `listProperties` and the one-line `showProperties`,
  `filterKeys` `["q", "owner_agent_id"]` and `filterProperties`, `decorateServiceRecord` in `recordTransform` after
  `item.proxy_url =`, and the action `transferOwnership`.

## 5. The Permissions resource

- [ ] 5.1 Tests first, new file `apps/admin-ui/tests/test_permissions_governance.test.ts`, covering the two scenarios of
  "Permissions show the grantor and the expiry". Then edit `apps/admin-ui/src/resources/permissions.ts`: the properties and
  lists, `filterKeys` `["q", "service_id", "agent_id", "grantor_agent_id"]`, and `recordTransform`.

## 6. The Access requests resource

- [ ] 6.1 Tests first, new file `apps/admin-ui/tests/test_access_requests_resource.test.ts` (it reads
  `apps/admin-ui/src/index.ts` as text for the registration), covering the scenario of "Access requests have their own
  resource" and the two of "An operator approves or denies a pending request"; red creates
  `apps/admin-ui/src/resources/access-requests.ts` exporting `AccessRequestsResource` with only its `RestResource`. Then fill
  in the options and the two actions, and in `apps/admin-ui/src/index.ts` import `AccessRequestsResource` and add its entry to
  `resources` right after the `PermissionsResource` entry.

## 7. The audit filter

- [ ] 7.1 Tests first, new file `apps/admin-ui/tests/test_audit_governance.test.ts` (reads
  `docs/architecture/contracts/events/audit-event.schema.json` with `path.resolve(__dirname, "../../../docs/...")`), covering
  the scenario of "The audit filter knows the new events"; it fails before the change. Then add the values to the three
  `availableValues` lists of `apps/admin-ui/src/resources/audit.ts`.
