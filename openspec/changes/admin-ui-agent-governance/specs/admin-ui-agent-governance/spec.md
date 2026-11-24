# Admin UI agent governance

## Purpose

The helpers, the one server-side read and the components behind the admin UI's views of agent roles, service ownership,
grants and access requests. Pure functions decide every label and body so that the behaviour is tested without a browser.

## ADDED Requirements

### Requirement: Pure helpers decide the labels and bodies
`apps/admin-ui/src/lib/agent-governance.ts` SHALL export:

```ts
export const AGENT_ROLE_VALUES: Array<{ value: string; label: string }>      // consumer, publisher
export function normalizeRole(value: unknown): "consumer" | "publisher"
export function ownerLabel(ownerAgentId: unknown): string
export function credentialLabel(service: Record<string, unknown>): string
export interface ExpiryBadge { state: "none" | "active" | "expired"; label: string }
export function expiryBadge(grant: Record<string, unknown>): ExpiryBadge
export function grantorLabel(grant: Record<string, unknown>): string
export function formatTtl(seconds: unknown): string
export function decorateServiceRecord(item: Record<string, unknown>): Record<string, unknown>
export function decorateGrantRecord(item: Record<string, unknown>): Record<string, unknown>
export function decorateAccessRequestRecord(item: Record<string, unknown>): Record<string, unknown>
export function transferBody(payload: Record<string, unknown> | undefined): { to_agent_id: string | null }
export function decisionBody(payload: Record<string, unknown> | undefined, kind: "approve" | "deny"):
  { ok: true; body: { ttl_seconds?: number; note?: string } } | { ok: false; error: string }
export function governanceErrorMessage(body: unknown, fallback: string): string
```
`normalizeRole` SHALL return `publisher` for `"publisher"` and `consumer` for anything else. `ownerLabel` SHALL return
`operators` for null, undefined, `""` and `"operators"`, else the id. `credentialLabel` SHALL return the label of
`getCredentialStatus({auth_scheme, current_key_version, status})` of `credential-status.ts`. `expiryBadge` SHALL return
state `expired` and label `Expired` when `expired` is true, else `none` and `No expiry` when `expires_at` is null or
absent, else `active` and `Expires <expires_at>`; it SHALL NOT read the clock. `grantorLabel` SHALL return `grantor_id` for
`grantor_type` `agent` (the word `agent` without an id) and `operator` otherwise. `formatTtl` SHALL return `<n> d` for a
positive multiple of 86400, `<n> h` for a positive multiple of 3600, `<n> min` for a positive multiple of 60, `<n> s` for
another integer, and `—` for anything that is not a finite integer. `decorateServiceRecord` SHALL add `owner` and `credential`;
`decorateGrantRecord` SHALL add `expiry` (the badge label), `expiry_state` and `grantor`; `decorateAccessRequestRecord`
SHALL add `action` (the `actions` array joined with `, `, or `—`) and `requested_ttl` (`formatTtl` of
`requested_ttl_seconds`); each SHALL keep every other key. `transferBody` SHALL return `{to_agent_id: null}` for a missing
payload, a missing, empty, blank or `operators` value, else the trimmed id. `decisionBody` SHALL read `ttl_seconds` (approve
only; empty means absent; a whole number from 60 to 7776000, as a number or digit string) and `note` (trimmed; empty means
absent; at most 500 characters) and SHALL return `{ok: false, error}` for an invalid value, with the error text `Lifetime
must be a whole number of seconds from 60 to 7776000.` or `Note must be at most 500 characters.`. `governanceErrorMessage`
SHALL map the body's `mintkey:code` to a message (`invalid_transfer_target` with `reason` `agent_not_publisher`: `The new
owner must be an agent with the publisher role.`; with `agent_not_active`: `The new owner must be an active agent.`;
`request_not_pending`: `This request is already <status>.`; `grant_conflict`: `The agent already holds a live grant with
another expiry; revoke it first, or deny this request.`; `requester_not_active`: `The requesting agent is no longer
active.`; `already_granted`: `The agent already holds a live grant for this service.`), else the body's non-empty `title`, else
`fallback`.

#### Scenario: roles, owners and credentials
- **WHEN** the helpers run with roles `"publisher"`, `"consumer"`, `"admin"`, `undefined`; owners `null`, `""`,
  `"operators"`, `"agent_A"`; and services `{auth_scheme: "bearer_token", current_key_version: 0}`, `{auth_scheme:
  "bearer_token", current_key_version: 2}`, `{auth_scheme: "none", current_key_version: 0}`
- **THEN** the roles are `publisher`, `consumer`, `consumer`, `consumer`; the owners `operators` three times, then
  `agent_A`; the credential labels `⚠ no credential`, `✓ configured v2` and `n/a (no auth)`

#### Scenario: the expiry badge and the grantor
- **WHEN** `expiryBadge` runs with `{expired: true, expires_at: "2020-01-01T00:00:00+00:00"}`, `{expired: false, expires_at:
  "2999-01-01T00:00:00+00:00"}`, `{expires_at: null}`, `{}`, and `{expired: false, expires_at: "2000-01-01T00:00:00+00:00"}`; and
  `grantorLabel` runs with `{grantor_type: "agent", grantor_id: "agent_B"}`, `{grantor_type: "agent"}`, `{grantor_type:
  "operator", grantor_id: "u1"}` and `{}`
- **THEN** the badges are `expired`/`Expired`, `active`/`Expires 2999-01-01T00:00:00+00:00`, `none`/`No expiry`, `none`/`No
  expiry`, and `active` with the 2000 date (the clock is not read); the grantors are `agent_B`, `agent`, `operator`, `operator`

#### Scenario: lifetimes and decorated records
- **WHEN** `formatTtl` runs with 172800, 7200, 1800, 90, 0, `"x"` and `null`; and the three decorators run on a service
  `{id: "svc_1", owner_agent_id: null, auth_scheme: "bearer_token", current_key_version: 0}`, a grant `{id: "perm_1", expired:
  true, expires_at: "2020-01-01T00:00:00+00:00", grantor_type: "agent", grantor_id: "agent_B"}` and a request `{id: "areq_1",
  actions: ["call"], requested_ttl_seconds: 3600}`
- **THEN** the lifetimes are `2 d`, `2 h`, `30 min`, `90 s`, `0 s`, `—` and `—`; the service gains `owner` `operators` and
  `credential` `⚠ no credential`, the grant `expiry` `Expired`, `expiry_state` `expired` and `grantor` `agent_B`, the request
  `action` `call` and `requested_ttl` `1 h`; every original key is unchanged

#### Scenario: the transfer and decision bodies
- **WHEN** `transferBody` runs with `undefined`, `{to_agent_id: ""}`, `{to_agent_id: " operators "}`, `{to_agent_id: null}`
  and `{to_agent_id: " agent_C "}`; and `decisionBody` runs for approve with `{ttl_seconds: "3600", note: " ok "}`, `{ttl_seconds:
  ""}`, `{ttl_seconds: 59}`, `{ttl_seconds: "1.5"}`, `{note: "x".repeat(501)}`, and for deny with `{ttl_seconds: "99999999",
  note: "no"}` and `undefined`
- **THEN** the transfer bodies are `{to_agent_id: null}` four times, then `{to_agent_id: "agent_C"}`; the decisions are
  `{ok: true, body: {ttl_seconds: 3600, note: "ok"}}`, `{ok: true, body: {}}`, the lifetime error twice, the note error,
  `{ok: true, body: {note: "no"}}` (the lifetime ignored) and `{ok: true, body: {}}`

#### Scenario: error messages
- **WHEN** `governanceErrorMessage` runs with each mapped body above (`request_not_pending` with `status` `approved`), `{title:
  "Agent not found"}`, `{"mintkey:code": "not_found"}` and `null`, with the fallback `Failed`
- **THEN** the messages are the texts above, with `This request is already approved.` for the request, then `Agent not
  found`, `Failed` and `Failed`

### Requirement: One server-side read gathers an agent's governance data
`apps/admin-ui/src/lib/governance-bff.ts` SHALL export `readHeaders(currentAdmin)`, `governanceUrls(tenantId, agentId)` and
`fetchGovernanceSummary({apiUrl, tenantId, agentId, currentAdmin}): Promise<GovernanceSummary>`. `readHeaders` SHALL return
`{Cookie: "mintkey_session=<token>"}` for a session token and add `X-Platform-Admin: "true"` only when `isPlatformAdmin` is
`true`. `governanceUrls` SHALL return the paths `owned_services` `/v1/tenants/<t>/services?owner_agent_id=<a>`,
`grants_received` `/v1/tenants/<t>/permissions?agent_id=<a>`, `grants_given` `/v1/tenants/<t>/permissions?grantor_agent_id=<a>`,
`requests_made` `/v1/tenants/<t>/access-requests?requester_agent_id=<a>` and `requests_incoming`
`/v1/tenants/<t>/access-requests?owner_agent_id=<a>&status=pending`, the ids percent-encoded.
`fetchGovernanceSummary` SHALL GET the five URLs with `readHeaders`, read each list under its key (`services`,
`permissions`, `access_requests`), and return `{owned_services, grants_received, grants_given, requests_made,
requests_incoming, errors}`; a response that is not ok or a `fetch` that throws SHALL give an empty list for that section and one
entry in `errors` naming the section, and SHALL NOT stop the others.

#### Scenario: urls and headers
- **WHEN** `governanceUrls("t1", "agent_A")` and `readHeaders` run for a session `{sessionToken: "tok"}`, a platform admin
  `{sessionToken: "tok", isPlatformAdmin: true}` and `null`
- **THEN** the five paths are exactly those above; the headers are the cookie, the cookie plus `X-Platform-Admin`, and `{}`

#### Scenario: the summary and its partial failure
- **WHEN** the fetch mock answers the five URLs with lists, and again with the fourth answering 500 and the fifth throwing
- **THEN** the first summary has each list in its section and no errors; the second has the first three lists, two empty
  sections and two entries in `errors`, and every URL was requested with the cookie header

### Requirement: Generic components render the new views
`apps/admin-ui/src/components/index.ts` SHALL register `PayloadActionForm` (`./actions/PayloadActionForm`),
`AgentGovernancePanel` (`./sections/AgentGovernancePanel`) and `GrantExpiryBadge` (`./properties/GrantExpiryBadge`).
`PayloadActionForm` SHALL render one text input per entry of `action.custom.fields` (`{name, label, hint?}`), a submit
button and a cancel link, and on submit call `ApiClient.recordAction` with `method` `post` and `data` the raw string values
by field name, then show the returned notice. `AgentGovernancePanel` SHALL call `recordAction` with `actionName`
`governanceSummary` for the record's id and render the five sections with their rows, the errors, and `GrantExpiryBadge`
for each grant. `GrantExpiryBadge` SHALL render `record.params.expiry` with the `data-testid` `grant-expiry-<state>`
of `record.params.expiry_state`.

#### Scenario: the components are registered
- **WHEN** `src/components/index.ts` is read as text
- **THEN** it contains the three `componentLoader.add` calls with those names and paths

#### Scenario: the form posts what was typed
- **WHEN** `PayloadActionForm` renders with the fields `ttl_seconds` and `note`, the values `600` and `ok` are typed and the form is
  submitted, with `recordAction` answering `{data: {notice: {message: "Done", type: "success"}}}`
- **THEN** `recordAction` was called once with `method` `post` and `data` `{ttl_seconds: "600", note: "ok"}`, and the notice
  `Done` is on screen

#### Scenario: the panel and the badge
- **WHEN** `AgentGovernancePanel` renders with a mocked `recordAction` returning a summary with one owned service, one grant
  received (`expiry_state` `expired`) and an error entry, and `GrantExpiryBadge` renders for `expiry_state` `active`
- **THEN** the panel shows the service row, the grant with `grant-expiry-expired`, and the error text; the badge shows
  `grant-expiry-active` with its label
