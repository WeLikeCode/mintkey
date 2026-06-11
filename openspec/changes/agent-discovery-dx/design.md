# Design — Agent Discovery DX

## Context

Audit (2026-06-11) of the agent-facing surfaces found: `mintkey_discover`'s `how_to_call` is generic boilerplate (discovery.py:153–171); `mintkey_describe_service` (discovery.py:340–399) omits `auth_scheme_details` and `your_constraints` even though agent-bootstrap.md:151–161 documents them and tools.yaml's `service_full` promises `explicit_proxy_url`; per-scheme injection behavior for all 16 `AuthScheme` values exists only in `proxy-plugin/internal/credential/injector.go:44–90`; `mintkey_get_openapi` returns a bare URL-or-null while tools.yaml:340–411 contracts a url/inline discriminated response; `services.openapi_url`/`openapi_etag` columns exist (changelog 004) but nothing tells operators to populate them. Dogfooding evidence: this very repo's operator keeps the call recipe in a personal CLAUDE.md because the wire doesn't carry it.

## Goals / Non-Goals

**Goals:** an agent with only an `mk_agent_` key self-serves discovery → understanding → first successful call, entirely from on-wire responses; one source of truth for per-scheme guidance; the bootstrap never promises what the wire doesn't deliver; OpenAPI specs reachable when operators register them.

**Non-Goals:** implementing mtls; new auth schemes; validating/transforming upstream OpenAPI content; admin-ui work; operator-authored per-service usage notes (future column); changing the broker/token flow.

## Decisions

**D1 — Single injection-hint table in `mcp_server/auth_schemes.py`, parity-gated against the proto enum.**
A dict keyed by auth-scheme string: `{injects, location, never_send, handled_by, status}` per scheme, mirroring injector.go. Both `discover` (compact one-liner) and `describe_service` (`auth_scheme_details`) render from it; the bootstrap markdown's cheat-sheet section is generated (or test-pinned) from the same table. A unit test parses vault.proto's enum and fails on any uncovered value — adding scheme #17 without a hint breaks CI. Alternative (docs-only in bootstrap.md) rejected: drifts again immediately.

**D2 — `describe_service` fills its advertised contract instead of trimming the docs.**
The promised fields are genuinely useful and cheap: `your_constraints` is one read of the caller's `permission_grants.constraints` JSONB (the table the tool already consults); `explicit_proxy_url` is string assembly from the existing proxy-base env; `auth_scheme_details` comes from D1 plus the per-credential `header_name`/`query_param` overrides where the metadata row has them. Trimming bootstrap.md to match today's thin response was rejected — it would codify the gap this change exists to close.

**D3 — `list_services` stays compact.**
It remains the cheap enumeration; its `hint` gains one line pointing at `describe_service`/`discover` for usage. Duplicating hints into every list item rejected (token bloat for large tenants).

**D4 — get_openapi: implement to the existing contract; fetch-on-request with etag, 1 MiB cap, no new storage.**
Inline mode fetches the registered URL server-side with `If-None-Match` from `services.openapi_etag`, updates the etag column, caps at 1 MiB, 10 s timeout, and never follows redirects off the registered host. Failures return `fetch_failed` with the URL so the agent can decide. A background cache/refresh job was rejected (speculative; fetch-on-request is enough until proven otherwise).

**D5 — Contract-first, additive-only; no ADR.**
tools.yaml output schemas gain the new optional fields before code lands. No new tools, endpoints, enums, error codes, or prefixes → none of ADR-0017.10/.11's ADR triggers fire. The pre-existing contract/implementation mismatch on `service_full` is resolved toward the contract.

**D6 — Honesty gates in CI.**
Two cheap mcp-server tests: (a) enum-parity (D1); (b) bootstrap-parity — extract backtick-quoted response field names from the discovery sections of agent-bootstrap.md and assert each exists in the corresponding response model. Keeps the trust property mechanical instead of editorial.

## Risks / Trade-offs

- **[Inline OpenAPI fetch is SSRF-shaped]** → only the operator-registered URL is fetched (operator-trusted input, same trust as `base_url`), redirects off-host refused, 1 MiB/10 s caps, response is passed through as opaque text (never evaluated).
- **[Constraints exposure]** → `your_constraints` reveals only the calling agent's own grant (it already learns limits empirically via 429s); other agents' grants are never returned.
- **[Bootstrap-parity test brittleness]** → scoped to the discovery-tool sections and to backtick-quoted field tokens; on false positives the test, not the docs, gets the targeted exemption list.
- **[Hint accuracy vs injector.go drift]** → the table cites injector.go lines; a comment in injector.go points back. True mechanical extraction from Go source rejected as over-engineering; the enum-parity test catches the common failure (new scheme, no hint).

## Migration Plan

Pure addition. New optional output fields; existing agent integrations unaffected. Bootstrap markdown rewrite ships in the same PR as the fields it documents.

## Open Questions

- None blocking. Future candidates noted in proposal Out-of-scope: operator-authored `usage_notes` column; admin-ui field for `openapi_url`.
