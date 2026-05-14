# Admin UI — UX rework specification (deep dive)

> **Purpose.** The current `admin-ui` is a thin AdminJS scaffold: it doesn't boot (no resource adapter registered — the current code half-imports `@adminjs/sql`, which we are replacing; see §0), list views would be empty even if it did, the landing screen is the default "Welcome to AdminJS" placeholder, auth-scheme fields are free-form text, there's no clear sign of which credential is attached to which service, and several flows have no working form. This document is the **authoritative UX spec for the admin-UI rework**. It refines `.kiro/specs/mintkey-mvp/design.md §5` ("Admin UI") and the long-lived-api-keys `requirements.md §9`/`design.md §5`; for the UI those docs should be updated to point here. The implementing prompt is `team/remediation/PROMPT_ADMIN_UI.md`.
>
> **Source of truth for field-level details:** `docs/architecture/contracts/rest/openapi.yaml` — the `AuthScheme` enum and the `RegisterCredentialRequest` discriminated union define exactly which fields each auth scheme needs. The UI form must match the contract; extend the contract (it's `M`-modifiable per ADR-0014.3) only if a scheme is genuinely missing a field it needs, and run the OpenAPI-parity gate after.
>
> **Non-negotiables (apply to every screen):** test-first (vitest/supertest unit + Playwright/browser integration); validate via tools (run the tests, paste the output, render the UI in a browser — no "looks fine" claims); end-to-end testing of the service-onboarding flow through the UI; surgical changes; Serena MCP for code navigation; never `--no-verify`; never edit `docs/architecture/**` to make a gate pass (if the contract is wrong, open an OQ).

---

## 0. Architectural rule + prerequisites

> **AdminJS uses the admin-api REST API for ALL data access — list, show, create, update, delete, and audit reads. AdminJS holds NO database connection** (no `@adminjs/sql`, no `pg`, no `connect-pg-simple`). The admin-api is the single front door: it owns the schema, owns the session, and **enforces RLS** (it sets `app.current_tenant` per request from the operator's session). AdminJS is a thin presentation layer:
> - **Reads** (`find` / `findOne` / `count` for every resource, plus audit) → `GET` the admin-api endpoint, relaying the operator's `mintkey_session` cookie. Admin-api scopes the result to the operator's tenant.
> - **Writes** (`create` / `update` / `delete`, plus the custom actions: Test Connection, Register/Rotate credential, Revoke, Rotate API key, etc.) → the admin-api endpoint with the `AdminUiSignedRequest` Ed25519 JWT in `Authorization: Bearer` (plus the relayed cookie).
> - **Session** is owned by admin-api (its `sessions` table). AdminJS's `authenticate()` POSTs `/v1/auth/internal-login`, relays admin-api's `Set-Cookie: mintkey_session=…` to the browser, and on every subsequent request validates the cookie by calling `GET /v1/auth/whoami` (caching the result in-process for a few seconds, so a multi-replica AdminJS works — admin-api is the shared state).
>
> This removes the old `@adminjs/sql` read path and the RLS-on-the-read-connection problem entirely. It also means a new component: a thin custom **`RestResource` adapter** for AdminJS (`admin-ui/src/lib/rest-resource.ts`) that maps AdminJS's data-layer interface (`find`, `findOne`, `create`, `update`, `delete`, `count`, `properties`) onto admin-api REST calls, with property schemas derived from the OpenAPI component schemas (or hand-declared per resource). (Use a maintained community REST adapter if one fits exactly; otherwise write the thin one — it's ~200–400 LOC and well-defined.)

These are the blockers — fix them as part of this work or coordinate with Phases 1–2 of `team/remediation/MEGA_PROMPT.md`:

| # | Blocker | Fix |
|---|---|---|
| **P0-1** | AdminJS declares `resource: "services"` etc. as bare strings and imports `@adminjs/sql` but never registers an adapter → `NoResourceAdapterError`, the container exits. | Remove `@adminjs/sql` and `pg` from `package.json`. Implement `RestResource`/`RestDatabase` (the thin custom adapter above) and `AdminJS.registerAdapter({ Database: RestDatabase, Resource: RestResource })`. Back every resource with admin-api REST calls. The app must start and `/admin` must render. |
| **P0-2** | `connect-pg-simple` writes to a `session` table that doesn't exist → 500 on first request; and there are two competing session middlewares. | AdminJS holds NO Postgres session store. Drop `connect-pg-simple`. The session is admin-api's (its `sessions` table). One auth path: `authenticate()` → `POST /v1/auth/internal-login` → relay the `mintkey_session` cookie; per-request, validate via `GET /v1/auth/whoami` (which **admin-api must implement** — it's currently a stub returning `{operator: null}`) with a short in-process cache. The OIDC path likewise terminates at admin-api. |
| **P0-3** | (admin-api side, dependency) The REST surface AdminJS now relies on isn't complete: every AdminJS resource needs a `GET` list + `GET` one; `GET /v1/auth/whoami` is a stub; `POST /v1/tenants/{tid}/services/{sid}/test` doesn't exist; credentials accept `value` but the UI sends `plaintext`; the permissions route the UI calls (`/v1/tenants/{tid}/permissions`) doesn't exist (real route is `/agents/{aid}/permissions`); state-changing routes don't verify the `AdminUiSignedRequest` JWT and the UI sends it in the wrong header; list responses don't include human-readable labels. | Per `MEGA_PROMPT.md` Phase 2 + the `ENDPOINT_COVERAGE.md` work. Specifically: (a) implement `GET /v1/auth/whoami` (read the `mintkey_session` cookie → return `{operator_id, email, tenant_id, is_platform_admin, memberships}`); (b) implement `POST .../services/{sid}/test`; (c) ensure a `GET` list + `GET` one exists for Services, Credentials (per service), Agents, Permissions, API Keys, Audit, Tenants — with cursor pagination (`?after&limit`), the filters/sort the UI needs, and **human-readable labels in list responses** (a permission row includes `agent_name` + `service_name`; a credential row includes `service_name`; etc., so AdminJS doesn't N+1); (d) fix the credential field name (`value`), the agent-nested permissions route, and the signed-JWT verification **per [ADR-0019](../../docs/architecture/01-architecture/adr/0019-admin-ui-bff-and-write-auth.md)**: every state-changing `/v1/tenants/...` route requires BOTH a valid, unexpired `mintkey_session` cookie AND a valid `AdminUiSignedRequest` Ed25519 JWT in `Authorization: Bearer` (signature ✓, `iss="mintkey/admin-ui"`, `aud="mintkey/admin-api"`, `exp ≤ iat+60s`, `jti` not in `admin_request_jti`), with `jwt.sub == session.operator_id` and `jwt.tnt == session.tenant_id` (and `session.is_platform_admin` when the "all tenants" view is asserted); the **effective identity** (tenant-context GUC + audit `actor_id`) is the **session's**, never the JWT's; reads require only the cookie. If running standalone, fix here. |

The UI work is "done" only when, with P0-1..P0-3 fixed, an automated browser test logs in with the bootstrap password, every resource list renders with data (sourced from admin-api REST calls) when data exists, and the service-onboarding flow below works through the UI.

---

## 1. The auth-scheme model (the dropdown, and the fields per scheme)

**Rule: anywhere the value is one of a fixed set, the UI uses a `<select>` dropdown — never a free-form text input.** That applies first and foremost to `auth_scheme`, but also to `agent_id`/`service_id`/`action` selectors, `isolation_mode`, statuses, etc.

The `auth_scheme` is a **property of the Service** (set once, on the Service form). The Service's credential is registered *of that scheme*; the Credential form for a service shows the scheme (read-only, inherited from the service) and collects only the scheme-specific values. Changing a service's auth scheme requires re-registering the credential.

### 1.1 The dropdown options (display label → enum value → fields)

| Display label | `auth_scheme` value | Form fields the operator fills | Secret? (write-only, never shown/returned) |
|---|---|---|---|
| **No authentication** | `none` *(see Gap G1 — add to the enum if missing)* | *(none)* | — |
| **API key — header** | `api_key_header` | `header_name` (text, default `X-API-Key`); `value` (the key) | `value` is secret |
| **API key — query parameter** | `api_key_query` | `param_name` (text, default `api_key`); `value` (the key) | `value` is secret |
| **Bearer token** | `bearer_token` | `value` (the token; goes in `Authorization: Bearer …`) | `value` is secret |
| **Basic auth (username / password)** | `basic_auth` | `username` (text); `password` | `password` is secret |
| **OAuth 2.0 — client credentials** | `oauth2_client_credentials` | `token_url` (text); `client_id` (text); `client_secret`; `scopes` (multi-text, optional); `audience` (text, optional) | `client_secret` is secret |
| **OIDC — client secret** | `oidc_client_secret` | `issuer` (text); `client_id` (text); `client_secret`; `scopes` (multi-text, optional) | `client_secret` is secret |
| **mTLS (client certificate)** | `mtls` | `client_cert_pem` (multiline); `client_key_pem` (multiline) — or a single combined PEM bundle field, per the contract | the whole bundle is treated as write-only |

The exact field names and the `value` encoding per scheme are defined by `RegisterCredentialRequest`'s discriminated variants in the OpenAPI — the UI form must produce a body that validates against the matching variant. Non-secret fields (`header_name`, `param_name`, `username`, `token_url`, `client_id`, `issuer`, `scopes`, `audience`, `client_cert_pem`) MAY be shown in list/show views; secret fields MUST be write-only — the admin-api never returns them after creation, and the show view never has access to them.

### 1.2 How the form behaves

- On the **Service** create/edit form: an `auth_scheme` `<select>` with the 8 labels above. Picking one shows a short help line ("Bearer token: the token Mintkey will inject as `Authorization: Bearer …` on every request to this service.").
- On the **Credential** create form (reached from the Service detail page, pre-scoped to that service): the scheme is shown read-only ("Auth scheme: API key — header"), and a **custom React `Edit` component** renders exactly the fields for that scheme (from §1.1). Secret fields are `type="password"` (or a textarea for PEM) with a "shown only now" note. On submit, the component assembles the `RegisterCredentialRequest` body for that variant and POSTs it (via the signed-request flow) to `POST /v1/tenants/{tid}/services/{sid}/credentials`.
- For `auth_scheme: none`: the Credential form has no fields; "Register credential" is replaced by a note "This service uses no authentication — nothing to configure" and the service's credential status reads "n/a (no auth)".

---

## 2. Per-screen specifications

### 2.1 Dashboard / onboarding (replace the default AdminJS landing — top priority)

A custom AdminJS `dashboard` (set `dashboard: { component, handler }` on the `AdminJS` instance). The `handler` queries the DB for counts and onboarding state; the `component` renders:

- **Header:** "Mintkey — credential broker for AI agents" + the logged-in operator's email + the active tenant slug (and, for a PlatformAdmin, the tenant switcher / "all tenants" toggle).
- **Quick-start checklist** (each item ticks ☑ when the corresponding resource exists; otherwise ☐ with a CTA button):
  1. **Register a backend service** — ☑ if ≥1 service exists, else ☐ → [Register a service] (→ Services → New).
  2. **Add its credential and test it** — ☑ if every service has a non-`none` credential of `current_key_version ≥ 1` (or is `auth_scheme: none`), else ☐ → [Configure credentials] (→ the first service missing one). Sub-status: "X of Y services have a credential; Z tested OK in the last 24h."
  3. **Create an agent** — ☑ if ≥1 agent, else ☐ → [Create an agent].
  4. **Grant the agent a permission** — ☑ if ≥1 permission grant, else ☐ → [Grant a permission].
  5. **Connect your LLM to MCP** — ☑ if ≥1 agent has been used (an `auth.agent_login.success`-type audit event exists), else ☐ → [Show MCP config] (→ the first agent's Connect panel).
- **At-a-glance counts:** `N services · M agents · K active permissions · L active API keys · P audit events (last 24h)`.
- **Empty state:** when nothing exists, the checklist *is* the screen, with a prominent "Register your first backend service" CTA and one short paragraph: "Mintkey brokers credentials between your AI agents and backend services. Register a service, attach its credential, create an agent, grant it access — your agent then discovers the service over MCP and calls it without ever seeing the real credential."
- **(Optional) stack-health strip:** admin-api ready, vault-adapter reachable, change-channel attached — small green/red dots reading `/v1/ready` and the relevant `/health` endpoints.

### 2.2 Login

The AdminJS login page with two options: "Sign in with username & password" (→ `POST /v1/auth/internal-login`) and "Sign in with Keycloak (SSO)". Lightly branded (Mintkey name, no AdminJS logo). The bootstrap operator's password comes from `./data/bootstrap-secrets/admin_password`. On a failed login, a generic "Invalid credentials" message (the timing/body-equalization is enforced server-side per ADR-0017.5 — the UI just shows the message). No further work needed beyond branding + making sure it actually works once P0-1/P0-2 are fixed.

### 2.3 Services

**List view** columns: `Name` · `Slug` · `Auth scheme` (the label, e.g. "API key — header", **never** the raw enum) · `Credential` (a clear status badge: ✓ **configured** v3 · ⚠ **no credential** · n/a (no auth) · ✗ **revoked**) · `Last test` (timestamp + ✓/✗, or "never tested") · `Created` · row actions: **Open**, **Test Connection** (disabled with a tooltip if no credential), **Edit**, **Delete**.

**Detail view** (the service's "home page"):
- Service metadata: name, slug, display name, description, `base_url` (the registered backend URL — informational), `openapi_url`, `auth_scheme` (label), status, created/updated.
- **"Credential" panel** — this is the *single source of truth for "which credential is attached to this service"*, and it must be unambiguous:
  - If no credential: a clear warning card — "⚠ No credential configured for this service. Agents can't call it yet." + a **[Register credential]** button (→ the credential form, pre-scoped to this service, scheme = this service's `auth_scheme`).
  - If `auth_scheme: none`: "This service uses no authentication. Nothing to configure." + a **[Test Connection]** button.
  - If a credential exists: a card showing — "**Credential configured** · scheme: API key — header (`X-API-Key`) · version **3** · status: current · last used: 2026-05-12 09:14 · **last test: 2026-05-12 11:04 — 200 OK** (latency 42 ms)" + buttons **[Test Connection now]** and **[Rotate credential]** (→ rotate form for a new version). It NEVER shows the credential value. (If the auth scheme has non-secret fields like `header_name`, `token_url`, `client_id`, `issuer`, `scopes` — show those here so the operator can sanity-check the config without re-typing the secret.)
- **"Test Connection"** action (a custom AdminJS `record` action, label "Test Connection", icon "Activity"): POSTs `{method, path, timeout_ms}` (defaults `GET /health 5000 ms`, with the option to override `method`/`path` in a small dialog) to `POST /v1/tenants/{tid}/services/{sid}/test`; shows the result inline as a result card — "✓ 200 OK · 42 ms" or "✗ 502 · timeout after 5000 ms" — and records `last test` on the service. The result must persist (re-rendered on the detail page), not just flash.
- **"Generate an agent for this service"** shortcut (optional, nice): a button that pre-fills the agent-create form, then suggests granting a permission on this service.

**Create / edit form:** proper field config (not raw column auto-render). `auth_scheme` is the §1 dropdown. `base_url` is validated client-side (must be `http(s)://`, and the server re-checks the SSRF/forbidden-destination rules). `openapi_url` optional. `allow_internal_urls` is a checkbox visible only to PlatformAdmins (and must actually be persisted by admin-api).

### 2.4 Credentials

A credential never exists without a service, and the UI must make that impossible to misunderstand:
- **No top-level "New" on the Credentials resource** — credential creation starts from the Service detail page's "Register credential" button (pre-scoped to that service, scheme fixed by the service). The Credentials resource's `new`/`edit`/`delete` default actions are hidden.
- **List view** columns: `Service` (the **first and most prominent** column — name + a link to the service) · `Auth scheme` (label) · `Version` · `Status` (current · deprecated · revoked) · `Last used` · `Last test` (✓/✗ + timestamp) · row actions: **Rotate** (→ rotate form: collects the new secret values for the same scheme; old version becomes `deprecated`, new becomes `current`), **Revoke** (with a confirm + reason). Filterable by `service_id` and `status`.
- **Detail view:** the same metadata + the non-secret config fields + the test history. Never the value.
- **Rotate form:** a custom `Edit` component that renders the §1 fields for the service's scheme (same component as create), labelled "New credential — the old version stays usable until you revoke it." On submit → `POST /v1/tenants/{tid}/services/{sid}/credentials` (the admin-api detects `key_version > 1` and treats it as a rotation; `rotate_from` field per the contract).
- **Create / rotate result:** the credential *value* is never echoed back. The result card says "✓ Credential v4 registered (scheme: API key — header). [Test Connection]" — and nudges the operator to test.

### 2.5 Agents

**List view** columns: `Name` · `Status` (active · revoked) · `API key fingerprint` (the 8-char fingerprint — **never** the key) · `MCP endpoint` · `# permissions` · `# API keys` · `Created` · row actions: **Open**, **Revoke** (confirm + propagation note), **Edit** (only if admin-api has an agent PATCH endpoint — if not, hide it and flag the gap).

**Detail view:**
- Agent metadata: name, description, status, `api_key_fingerprint`, `mcp_endpoint`, rate limit, created/updated.
- **"Connect" panel** — the affordance for wiring the agent into an LLM/MCP client. Shows a copy-able JSON snippet:
  ```json
  {
    "mcpServers": {
      "mintkey": {
        "url": "<mcp_endpoint>",
        "headers": { "Authorization": "Bearer <AGENT API KEY>" }
      }
    }
  }
  ```
  - **Immediately after agent creation:** the snippet shows the real, one-time API key, inside a copy-box modal with a clear "**Store this now — it's shown only once.**" warning and a "I've saved it" confirm before navigating away. NOT a transient flash banner.
  - **On any later visit:** the snippet shows `<your-saved-api-key>` as a placeholder + a note "the key was shown once at creation; if you've lost it, [rotate the agent's key]" (if an agent-key-rotation endpoint exists — if not, the note says "create a new agent" and flag adding key-rotation as a gap).
- **"Permissions" panel:** the agent's grants — `Service · Action · Constraints summary · Created` — with a **[Grant a permission]** button (→ permission form pre-filled with this agent).
- **"API Keys" panel:** the agent's classical `mk_svckey_…` keys — `Fingerprint · Service · Allowed actions · Expires · Last used · Status · [Revoke] [Rotate]` — with a **[Create API key]** button (→ the API-key form pre-filled with this agent).
- **Create form:** name + description; on success → the Connect panel with the one-time key.

### 2.6 Permissions

**Create / edit form** — every selector is a dropdown, not free-form ULID text:
- `Agent` — `<select>` of the tenant's agents (label = agent name; value = `agent_id`).
- `Service` — `<select>` of the tenant's services (label = service name; value = `svc_id`).
- `Action` — `<select>` of the selected service's `actions` (loaded after the service is picked). Fall back to a free-text input only if the service has no declared `actions` list, with a note.
- `Constraints` — a **structured sub-form** for the closed `Constraints` schema (ADR-0016.4): four optional sections — `rate_limit` (`requests_per_second`, `burst`), `time_window` (`timezone` dropdown, `days` multi-select, `start_local`, `end_local`), `request_path_prefix` (text), `source_ip_allowlist` (multi-text of CIDRs). A "raw JSON" toggle is acceptable as an *escape hatch*, but the default is the structured form; client-side validation rejects unknown keys (`additionalProperties: false`). On submit → `POST /v1/tenants/{tid}/agents/{agent_id}/permissions` (the **agent-nested** path — the route the contract defines; fix the UI's current wrong path).
- **List view:** `Agent` · `Service` · `Action` · `Constraints` (a compact summary, e.g. "rate ≤ 10/s · Mon–Fri 09:00–17:00 Europe/Bucharest") · `Created` · row action: **Revoke** (confirm; emits the change event so the proxy denies new tokens for this grant).

### 2.7 API Keys (classical `mk_svckey_…`, per ADR-0018)

**Create form** (reached from an Agent's "API Keys" panel, or a top-level "Create API key" with an agent picker):
- `Agent` — `<select>` of agents.
- `Service` — `<select>` of services.
- `Allowed actions` — multi-`<select>`, limited to the chosen agent's grants for the chosen service (server re-validates: a key can't exceed the agent's grants).
- `Expires at` — a datetime picker; required if the operator policy `api_key.require_expiry` is set, and bounded by `api_key.max_expiry_days`.
- `Constraints` — the same structured sub-form as Permissions; `source_ip_allowlist` required if `api_key.require_ip_allowlist`.
- On submit → `POST /v1/tenants/{tid}/agents/{aid}/api-keys`. The response's one-time `plaintext_key` is shown in a copy-box modal — "**Store this now — shown only once.** Use it as `Authorization: Bearer mk_svckey_…` against `<proxy>/v1/call/<service_id>/<path>`." — with an "I've saved it" confirm. The `new`/`edit`/`delete` default AdminJS actions are hidden; key creation is *only* via this form.

**List view:** `Fingerprint` · `Agent` (name) · `Service` (name) · `Allowed actions` · `Expires` · `Last used` (blank = never used → an "issued but unused" hygiene flag) · `Status` (active · expired · revoked) · row actions: **Revoke** (confirm + reason), **Rotate** (creates a new key — copy-box modal — old stays active until revoked; shows the rotated-from/to link until the old is revoked). Never the plaintext.

### 2.8 Audit

Read-only. **List view:** `Time` (RFC 3339 UTC) · `Event type` · `Actor` (operator/agent/system + id) · `Target` (type + id) · `Outcome` (success/denied/error, where applicable) — with filters for `event_type`, `agent_id`, `service_id`, and a time-range picker; cursor pagination (the `?after=<event_id>` form). **Detail view:** the full event + the **hash-chain linkage** shown explicitly (`prev_hash` → this event's `hash`) so an operator can see the chain is intact. (Verifying the whole chain is a separate job — the UI just displays the linkage.) The list is sourced from admin-api's `GET .../audit` endpoint (RLS-scoped from the operator's session) — it must actually show rows.

### 2.9 Tenants (PlatformAdmin only)

**List view:** `Slug` · `Display name` · `Isolation mode` (a dropdown on create: `row` (default)) · `Status` (active · suspended) · `Created` · actions: **Open**, **Edit** (needs an admin-api `PATCH /v1/tenants/{id}` — add it if missing), **Suspend/Resume** (if a tenant-suspend flow exists; if not, flag it). **Create form:** slug, display name, isolation mode dropdown. **"All tenants" toggle** (visible only to PlatformAdmins): when on, the AdminJS REST calls signal `platform_admin_view: true` to admin-api (a query param on reads; the same claim in the signed request for writes), so admin-api sets `app.platform_admin_view='on'` for the request — cross-tenant lists then work — and every cross-tenant read emits a `platform_admin.access` audit event. When off, all views are scoped to the operator's tenant.

---

## 3. Cross-cutting UX rules

1. **No free-form where an enum exists.** `auth_scheme`, `isolation_mode`, statuses, `agent_id`/`service_id`/`action` selectors — all `<select>`. Show human labels, store the enum value.
2. **Secrets are write-only.** Any credential value, password, client secret, private-key PEM, agent API key, or `mk_svckey_…` is collected once, never returned by admin-api after creation, never displayed in list/show views.
3. **One-time secrets get a real UI.** Agent API keys, classical API keys, and the rotated-credential acknowledgement appear in a copy-box modal with a "shown only once" warning and an explicit "I've saved it" confirm — never a transient flash that disappears on the next click/navigation.
4. **Every relationship is visible and unambiguous.** A credential always shows its service (first column); a service always shows its credential status; an agent shows its permissions and its API keys; a permission/API-key shows its agent and service; an audit event shows its actor and target. No floating records.
5. **State badges, not raw fields.** "✓ configured v3", "⚠ no credential", "✗ revoked", "active / expired / revoked", "last test: 2026-05-12 — 200 OK" — colour-coded, consistent.
6. **All data access goes through the admin-api REST API — reads and writes; AdminJS holds no database connection** (§0). Reads (`find`/`findOne`/`count`, audit): `GET` the admin-api endpoint, relaying the operator's `mintkey_session` cookie — admin-api enforces RLS from the session's tenant. Writes (`create`/`update`/`delete` + the custom actions): the admin-api endpoint with the `AdminUiSignedRequest` Ed25519 JWT in `Authorization: Bearer` (plus the cookie). The `RestResource` adapter (§0, P0-1) wires every resource to these calls. No `@adminjs/sql`, no `pg`, no `connect-pg-simple`.
7. **Errors are surfaced clearly** — admin-api's RFC-9457 problem responses (`title`, `mintkey:code`) are shown as the notice, not swallowed.
8. **Branding** — Mintkey name, no AdminJS logo; a consistent nav order: Dashboard → Services → Agents → Permissions → API Keys → Audit → Tenants (PlatformAdmin).

---

## 4. Testing requirements (mandatory — this is how "done" is judged)

For **every** screen and every behaviour above:

- **Unit (vitest + supertest):** the resource handlers and the dashboard handler — pick each `auth_scheme` from the dropdown and assert the right fields render and the right `RegisterCredentialRequest` variant is POSTed; the Test-Connection action POSTs the right body and renders the result; the Connect panel renders the right snippet; the create-agent / create-API-key flows return the one-time secret and the list never shows it; the Permissions form sends the agent-nested path with the structured constraints; the dashboard checklist reflects DB state. These tests must actually drive the handlers with mock `(request, response, context)` — not just assert object shapes.
- **Browser/integration (Playwright, or supertest against the running container):** boot the `admin-ui` container against a real testcontainer Postgres (+ a seeded bootstrap operator), log in with the bootstrap password, and assert: the dashboard renders the checklist (and the empty state when nothing exists); every resource list renders (with data when seeded); the auth-scheme dropdown shows the labels and the conditional fields appear; the Test-Connection result is shown; the one-time-key modal appears and the key isn't in the list view afterward.
- **End-to-end through the UI (the headline test for this work):** a Playwright test that walks the **service-onboarding flow** entirely in the browser against the live `docker compose` stack — log in → **register a service** (pick "API key — header" from the dropdown, set `X-API-Key`, base_url = the mock backend) → **register the credential** (the conditional form, paste the value) → **click Test Connection** → see "✓ 200 OK" → see the service detail page now shows "Credential configured v1 · last test: … 200 OK" → **create an agent** → see the one-time key in the modal, copy it → **grant a permission** (agent dropdown, service dropdown, action dropdown) → open the agent's Connect panel → see the MCP config snippet with the key. Assert each step. This must pass in CI.
- **Parity gates:** if the OpenAPI `RegisterCredentialRequest` variants or the `AuthScheme` enum are touched (e.g. adding `none`), the OpenAPI-parity gate and the SQLAlchemy-mirror gate must pass; every fenced ```mermaid``` block still renders with `mmdc`.
- **Validate via tools, not claims.** Run all of the above; paste the test-runner output and the Playwright run summary (and at least one screenshot or DOM assertion) in the report. "It looks good" is not acceptable. No `assert true`, no `pytest.skip`/`test.skip` to dodge a gap, no mocking the thing under test.

---

## 5. Gaps this rework also closes (carry them through)

- **G1 — `auth_scheme: none`.** Add `none` to the `AuthScheme` enum in lock-step across `openapi.yaml`, `mcp/tools.yaml` (`$defs/auth_scheme`), `events/audit-event.schema.json`, `events/change-event.schema.json`, and `vault.proto`; the proxy injects nothing for it; a `none` service has no credential rows but `request_token` still works (the brokered-token gate still enforces scope/tenant/revocation). Small ADR or amend ADR-0016.5. Then the "No authentication" dropdown option is real end-to-end.
- **G2 — `get_openapi` with no doc.** (MCP-side, but relevant: the Service form's `openapi_url` is optional.) Add a `{kind: none}` variant to `get_openapi`'s output for services without an OpenAPI doc.
- **G3 — agent-key rotation.** If there's no endpoint to rotate an agent's API key without revoking the agent, add one (`POST /v1/tenants/{tid}/agents/{aid}/rotate-key` → new one-time key) — the Connect panel's "lost your key?" path needs it. If you'd rather not, the panel says "create a new agent" and this is left as a documented limitation.
- **G4 — `PATCH /v1/tenants/{id}`** (admin-api) — the Tenants edit action needs it.
- **G5 — agent `PATCH`** (admin-api) — the Agents edit action needs it; otherwise hide the edit action.

---

## 6. Definition of Done for the admin-UI rework

All green, with command/screenshot proof:
1. P0-1..P0-3 fixed: the `admin-ui` container starts (the custom `RestResource` adapter is registered — no `NoResourceAdapterError`; AdminJS has no DB connection), `/admin/login` returns 200, login with the bootstrap password lands on the dashboard, every resource list renders with data (sourced from admin-api REST calls) when data exists.
2. The dashboard is the custom onboarding component (checklist + counts + empty state) — not the default AdminJS landing.
3. The `auth_scheme` field is a dropdown everywhere it appears, with the 8 labels from §1.1; the Credential form renders exactly the scheme-specific fields; secrets are write-only.
4. "Test Connection" exists, is reachable from the Services list and the Service detail page, POSTs to the `/test` endpoint, and shows + persists the result.
5. The credential↔service relationship is unambiguous on every relevant screen (the Service detail "Credential" panel; the Credentials list with `Service` as the first column).
6. Every other screen (Agents incl. the Connect panel, Permissions with dropdowns + structured constraints, API Keys, Audit, Tenants) matches §2.
7. The unit, browser, and **end-to-end-through-the-UI** tests in §4 all pass, in CI; the parity gates pass.
8. `git status` clean; no `--no-verify`; no edits to `docs/architecture/**` to pass a gate (only the deliberate G1 enum addition, which then passes the parity gate).
