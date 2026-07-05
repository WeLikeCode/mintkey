# Tailscale Service Template

## Why

Operators running Tailscale for their organisation's mesh VPN want their AI
agents to manage the tailnet — list devices, read/authorize machines,
manipulate ACL tags, inspect DNS settings — without ever handing the agent a
long-lived Tailscale credential. Mintkey already brokers this pattern for
GitHub, Stripe, Cloudflare, and others via one-click **service templates**
(`apps/admin-api/src/admin_api/templates/service_templates.yaml`), instantiated
through `POST /v1/tenants/{tid}/services/from-template`.

There is no Tailscale template today, so an operator has to hand-enter the base
URL, auth type, OAS URL, credential hint, and test path from scratch — and get
the `tskey-` prefix and the `-` default-tailnet convention right by hand. A
pre-configured template removes that friction and encodes the correct defaults
once.

Tailscale authenticates the REST API with a **plain `Authorization: Bearer`
token** — either a personal API access token (`tskey-api-...`) or an OAuth2
client-credentials access token. Both land as a bearer token, so this maps
directly onto Mintkey's existing `bearer_token` auth type with Kong injecting
the credential in-flight. **No new auth scheme, no new proxy route, no new
credential injector** is required — this is purely a catalog entry plus its
documentation.

## What Changes

- **New `tailscale` HTTP service template** appended to `service_templates.yaml`
  (`kind: http_service`, the default). It sets:
  - `base_url: https://api.tailscale.com`
  - `auth_type: bearer_token`
  - `category: networking`
  - `openapi_spec_url` pointing at Tailscale's published API reference
  - a `credential_hint` documenting the `tskey-api-...` / `tskey-client-...`
    prefixes
  - `test_path: /api/v2/tailnet/-/devices` (200 with a valid token; `-` resolves
    to the caller's default tailnet)
- **One-line `docs/HOW-TO.md` catalog mention** in the service-templates list so
  the template is discoverable in the operator docs.
- **ZERO wire-contract changes**: no OpenAPI path additions, no MCP tool
  additions, no `vault.proto` enum change, no Liquibase changeset, no
  SQLAlchemy mirror change. Agents call the registered service through the
  existing generic HTTP proxy path exactly as they do for GitHub or Stripe.

## Capabilities

### Modified Capabilities

- `service-template-catalog`: adds one pre-configured Tailscale entry to the
  read-only YAML catalog surfaced by `GET /v1/service-templates` and the Admin
  UI "add from template" flow. Additive only — no existing template changes,
  no schema/model change (the `ServiceTemplate` Pydantic model and
  `bearer_token` auth type already cover every field the entry uses).

### New Capabilities

<!-- None. No new auth scheme, proxy route, MCP tool, or DB surface. This is a
     data-only addition to an existing capability. -->

## Impact

- **`apps/admin-api/src/admin_api/templates/service_templates.yaml`**: one new
  list entry under `templates:`. No change to `models.py`, `registry.py`, or
  the `/v1/service-templates` handlers — the loader validates the entry against
  the existing `ServiceTemplate` model at import time.
- **`docs/HOW-TO.md`**: one row/line added to the service-template catalog list.
- **Tests**: extend the existing template-registry test to assert the
  `tailscale` template loads and validates; no new test file required.
- **No changes** to: `openapi.yaml`, `tools.yaml`, `audit-event.schema.json`,
  `vault.proto`, `proxy-plugin` credential injection, any Liquibase changelog,
  the SQLAlchemy mirror, or any ADR (the `bearer_token` scheme and the
  service-template mechanism are already Accepted architecture).
- **No ADR needed**: this neither adds a wire surface nor changes a guardrail;
  it uses only Accepted mechanisms (service templates + `bearer_token`
  injection via Kong).
