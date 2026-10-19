# Design — Tailscale Service Template

## Context

Mintkey service templates are read-only seed data loaded from
`apps/admin-api/src/admin_api/templates/service_templates.yaml` at import time
by `apps/admin-api/src/admin_api/templates/registry.py`, validated against the
`ServiceTemplate` Pydantic model in `.../templates/models.py`. An operator picks
a template in the Admin UI, supplies the credential, and Mintkey creates a
`services` row + a vault credential; agents then call the upstream through Kong,
which injects the real credential per-request (never exposed to the agent).

The Tailscale REST API (base `https://api.tailscale.com`, all paths under
`/api/v2/`) authenticates every request with a plain `Authorization: Bearer
<token>` header. This is exactly what the existing `bearer_token` auth type
does — Kong holds the token in vault and injects the header. So adding Tailscale
is a **data-only** change: one YAML entry. No code, no new auth scheme, no proxy
route, no DB migration.

### Facts confirmed against Tailscale's docs (2026-07)

- Base URL: `https://api.tailscale.com`; API version prefix `/api/v2/`.
  (Tailscale API reference — https://tailscale.com/docs/reference/tailscale-api)
- **Personal API access token**: created in the admin console → Keys; prefix
  `tskey-api-...`; case-sensitive; configurable expiry 1–90 days; used as
  `Authorization: Bearer tskey-api-...`.
- **OAuth2 client credentials**: `client_id` + `client_secret`
  (secret prefix `tskey-client-...`); token endpoint
  `POST https://api.tailscale.com/api/v2/oauth/token` (standard OAuth2
  client-credentials grant); returns a bearer access token that **expires after
  1 hour and cannot be renewed** (mint a new one before expiry). Scopes are
  selected per client, e.g. `devices:core`, `dns:read`, `auth_keys`, `all`.
  (Tailscale OAuth clients — https://tailscale.com/docs/features/oauth-clients)
- `-` is a valid alias for the authenticated principal's **default tailnet**,
  so `/api/v2/tailnet/-/devices` works without hard-coding an org name.
- Key endpoints agents will use:
  - `GET  /api/v2/tailnet/{tailnet}/devices` — list devices
  - `GET  /api/v2/device/{deviceId}` — device details
  - `POST /api/v2/device/{deviceId}/authorized` — authorize a machine
  - `POST /api/v2/device/{deviceId}/tags` — set ACL tags
  - `DELETE /api/v2/device/{deviceId}` — remove a device
  - `GET/POST /api/v2/tailnet/{tailnet}/acl` — read/update the policy file (ACLs)
  - `GET /api/v2/tailnet/{tailnet}/dns/nameservers|preferences|searchpaths` — DNS
  - `GET/POST /api/v2/tailnet/{tailnet}/keys` — list/create auth keys

## Goals / Non-Goals

**Goals**
- One correctly-defaulted `tailscale` template operators can instantiate in one
  click, with the `tskey-` prefixes and `-` default-tailnet convention baked in.
- A `test_path` that returns 200 with a valid token to validate the credential
  at registration time.
- Discoverability: the template shows up under `category: networking`.

**Non-Goals**
- **No OAuth2 client-credentials auth scheme.** Mintkey exchanging a
  `tskey-client-...` secret for a 1-hour token at the proxy would be a new auth
  scheme (like `oauth2_password_grant` / `google_service_account`) — out of
  scope; see D2 and Open Questions.
- No new MCP tool — agents use the generic brokered-HTTP call path.
- No proxy-plugin change, no `vault.proto` enum change, no DB schema change.
- No bundling/mirroring of the Tailscale OAS into the repo.

## Decisions

**D1 — `auth_type: bearer_token` with a personal API access token as the
documented default.**

Both Tailscale auth modes ultimately present `Authorization: Bearer <token>`.
The personal API access token (`tskey-api-...`) is a static string the operator
pastes once — it drops straight into the existing `bearer_token` injector with
zero new machinery. This is the Simplicity-First choice and matches how the
`github`, `openai`, `slack`, and `stripe` templates already work.

Trade-off: personal API tokens expire in 1–90 days, so the operator must rotate
the vault credential before expiry (same rotation story as GitHub PATs). This is
acceptable for a first cut and is called out in `config_notes`.

**D2 — OAuth2 client-credentials is documented but deferred, not implemented.**

The longer-lived, auto-rotating path is OAuth2 client credentials: Mintkey would
hold `client_id` + `tskey-client-...` secret, `POST` them to
`/api/v2/oauth/token`, cache the 1-hour bearer, and inject it. That is
genuinely better operationally (no manual token rotation), **but it is a new
auth scheme** — it needs a vault-adapter token-exchange path, a `vault.proto`
enum value, an OpenAPI enum addition, and proxy injection logic (the
`oauth2_password_grant` and `google_service_account` templates are the
precedents). The task scope is explicitly "a pre-configured template, NOT a new
auth scheme." So the template ships with `bearer_token` and the OAuth path is
recorded as a follow-up (OQ-TS-1). `config_notes` and the `credential_hint`
mention the OAuth alternative so operators know it exists.

**D3 — `test_path: /api/v2/tailnet/-/devices`.**

This is a read-only GET that returns 200 with any valid token that has at least
device-read scope, and `-` avoids hard-coding a tailnet org name. It is the
lowest-privilege, most-broadly-available endpoint suitable for credential
validation. (A token scoped to `dns:read` only would 403 here; that is
acceptable — the template's primary use case is device/tailnet management, and
the credential-validation check legitimately confirms device-read access.)

**D4 — `openapi_spec_url` points at Tailscale's published API reference page.**

Tailscale does not publish a stable, versioned raw OAS download URL (JSON/YAML)
at a documented location; the canonical, always-current reference is the
interactive docs at `https://tailscale.com/api`. Several existing templates
already set `openapi_spec_url` to a docs/GitHub-tree page rather than a raw spec
(`heroku`, `datadog`, `azure-devops`, `cloudflare`, `pagerduty`), so this is
consistent with the catalog's convention. If Tailscale later publishes a raw
OAS URL, it is a one-line follow-up to swap it in (OQ-TS-2).

**D5 — `category: networking`.**

The task allowed `networking` or `infrastructure`. Tailscale is a mesh-VPN /
network-connectivity product; `networking` is the more precise fit and creates a
new, self-describing category bucket. (The catalog has no fixed category enum —
`category` is a free-string field on `ServiceTemplate`, so a new value is safe.)

## The exact YAML entry to add

Append under the `# ── HTTP service templates` section of
`apps/admin-api/src/admin_api/templates/service_templates.yaml`:

```yaml
  - template_id: tailscale
    name: tailscale
    display_name: Tailscale
    description: "Tailscale mesh-VPN control API — list/authorize/remove devices, manage ACL tags, inspect DNS settings, and manage tailnet auth keys. Uses a Tailscale API access token as a bearer credential."
    base_url: https://api.tailscale.com
    auth_type: bearer_token
    openapi_spec_url: https://tailscale.com/api
    category: networking
    version: "1.0.0"
    config_notes: "Paste a Tailscale API access token (admin console → Settings → Keys → Generate access token). Tokens expire in 1–90 days — rotate the vault credential before expiry. Alternatively an OAuth2 client-credentials access token works as a bearer, but Mintkey does not yet perform the token exchange (OAuth support is a follow-up); for now supply a personal access token. The `-` in test_path resolves to the token's default tailnet."
    credential_hint:
      field: token
      help: "Tailscale API access token from the admin console Keys page. Needs at least device-read scope (e.g. devices:core) for the validation check to pass."
      format: "tskey-api-... (personal access token) or an OAuth2 access token"
    test_path: /api/v2/tailnet/-/devices
```

### Why this validates against the model

`ServiceTemplate` (models.py) requires `template_id, name, display_name,
category, version`; `version` accepts semver (`"1.0.0"` passes `_SEMVER_RE`).
`credential_hint` uses the simple `field/help/format` form that
`CredentialHint` supports. `auth_type: bearer_token` is a free string on the
model and a known injector scheme in the proxy. Every field is already covered —
no model change.

## Scopes / permissions agents need

Scopes are a property of the **Tailscale token the operator mints**, not of the
Mintkey template. Guidance for `config_notes` / HOW-TO:

- Device management (list/authorize/tag/remove): `devices:core`.
- Read DNS settings: `dns:read` (or `dns:write` to change them).
- Manage auth keys: `auth_keys`.
- Broad access (dev/testing only): `all`.

Recommend operators mint a **least-privilege** token (e.g. `devices:core` for a
device-management agent) rather than `all`. Mintkey's per-agent
`permission_grants.constraints` (path/method allowlists) further scope what the
agent may call through the proxy — that is orthogonal to the Tailscale token
scope and enforced by Mintkey, unchanged by this template.

## Implementation steps (minimal)

1. Add the YAML entry above to `service_templates.yaml`.
2. Add one catalog line to `docs/HOW-TO.md`'s service-template list.
3. Extend the existing template-registry test to assert the `tailscale` entry
   loads and validates (`registry.get("tailscale")` is not None, `auth_type ==
   "bearer_token"`, `base_url == "https://api.tailscale.com"`,
   `test_path == "/api/v2/tailnet/-/devices"`).
4. Run YAML-load + registry import + the admin-api unit suite.

## Risks / Trade-offs

- **[API token expiry — 1–90 days]** → Manual rotation, same as GitHub PAT
  templates. Documented in `config_notes`. Mitigated long-term by the deferred
  OAuth2 path (OQ-TS-1).
- **[`test_path` requires device-read scope]** → A token minted with only
  `dns:read` would fail credential validation. Acceptable: the template is
  primarily for device/tailnet management; the check legitimately confirms the
  common-case scope. Documented in the `credential_hint.help`.
- **[`openapi_spec_url` is a docs page, not a raw OAS]** → `mintkey_get_openapi`
  cannot return an inline machine-readable doc for this service; agents get the
  human docs URL. Consistent with several existing templates. Follow-up OQ-TS-2.
- **[`-` default-tailnet resolution]** → Relies on the token being scoped to a
  single default tailnet; correct for the overwhelmingly common single-tailnet
  operator. Multi-tailnet operators can register per-tailnet services by editing
  `test_path`/calls to a concrete tailnet name after instantiation.

## Open Questions

- **OQ-TS-1**: Add a first-class `oauth2_client_credentials` auth scheme so
  Mintkey exchanges `tskey-client-...` for a 1-hour token and auto-rotates
  (removing manual API-token rotation). New auth scheme → needs an
  ADR/proposal + `vault.proto` enum + proxy injector (≤ 3 proxy files per
  S-MOD-1). Track operator demand first.
- **OQ-TS-2**: If Tailscale publishes a stable raw OAS (JSON/YAML) download URL,
  swap `openapi_spec_url` to it so `mintkey_get_openapi` can serve a
  machine-readable spec.
