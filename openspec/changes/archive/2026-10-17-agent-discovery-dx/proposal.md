# Agent Discovery DX

## Why

An agent connecting to Mintkey today can list services and call the proxy, but cannot self-serve the *how*: per-auth-scheme injection behavior lives only in proxy-plugin Go source, `mintkey_describe_service` silently omits fields the bootstrap markdown explicitly promises (`auth_scheme_details`, `your_constraints`), `how_to_call` is generic boilerplate, and `services.openapi_url` exists in the schema but operators are never told to populate it — so `mintkey_get_openapi` usually returns null. Agents succeed by trial and error or by reading our source code; the bootstrap document promising nonexistent fields actively damages trust.

## What Changes

- **Per-auth-scheme guidance on the wire**: `mintkey_discover` and `mintkey_describe_service` gain an `injection_hint` — a one-liner per scheme stating exactly what the proxy injects and where (e.g. `bearer_token` → "proxy sets `Authorization: Bearer <secret>`; never send your own upstream auth header"), derived from a single table mirroring `proxy-plugin/internal/credential/injector.go` for all 16 schemes, including explicit "handled by the SSH/email proxy, not HTTP" and "mtls: not implemented" statuses.
- **`describe_service` honors its advertised contract**: actually return `auth_scheme_details` (injection point, header/query name, format) and `your_constraints` (the calling agent's rate limit, time window, path prefix, source-IP allowlist from its permission grant), plus the `explicit_proxy_url` already promised in tools.yaml.
- **One consistent discovery story**: landing page → bootstrap → list_services → describe_service each link to the next step; stale bootstrap sections rewritten to match reality; a per-scheme cheat-sheet section added to the bootstrap markdown generated from the same injection table (single source of truth).
- **OpenAPI exposure**: `mintkey_get_openapi` implements the inline mode already defined in tools.yaml (fetch + cache via the existing `openapi_etag` column, size-capped); `describe_service` reports an `openapi.status` (`available` / `not_registered` / `fetch_failed`); HOW-TO and admin registration docs tell operators to set `openapi_url`.
- **No new ADR required**: all changes are additive output fields on existing tools (documented contract-first in tools.yaml) or implementations of already-contracted-but-unbuilt behavior; no new closed-enum values, prefixes, or endpoints (per ADR-0017.10 boundaries).

## Capabilities

### New Capabilities
- `service-usage-guidance`: per-scheme injection hints, honest `describe_service` metadata (auth details, constraints, proxy URLs), consistent cross-linked discovery surfaces, accurate bootstrap.
- `openapi-exposure`: operator-populated OpenAPI URLs surfaced and optionally inlined to agents, with status reporting and caching.

### Modified Capabilities
<!-- none — existing specs do not cover these surfaces at requirement level -->

## Impact

- **Contracts**: `docs/architecture/contracts/mcp/tools.yaml` — extend `how_to_call` / `service_full` output schemas (additive); reconcile the documented-but-unimplemented `service_full` fields. No openapi.yaml changes (no new REST endpoints). No vault.proto changes.
- **Code**: `apps/mcp-server/src/mcp_server/tools/discovery.py` (the four discovery tools), new `auth_schemes.py` injection table, `skills/agent-bootstrap.md`, `tools/landing.py`; possibly a small `services` read in admin-api docs only (no admin-api code expected).
- **Docs**: `docs/HOW-TO.md` service-registration section (openapi_url guidance); bootstrap markdown.
- **Tests**: mcp-server unit tests per tool field; a parity test asserting the injection table covers every `AuthScheme` enum value (fails when a 17th scheme is added without a hint); bootstrap-vs-reality test (every field name the markdown promises exists in the corresponding tool response).
- **Out of scope**: new auth schemes, mtls implementation, proxying/validating upstream OpenAPI content beyond size/etag caching, admin-ui changes, per-service custom usage docs authored by operators (possible future: a `usage_notes` column).
