# Tasks — Agent Discovery DX

## 1. Contract (tools.yaml, additive)

- [ ] 1.1 Extend `how_to_call` schema in tools.yaml with `injection_hint` (object: injects, location, never_send, handled_by, status); extend `service_full` with `auth_scheme_details`, `your_constraints`, `explicit_proxy_url`, `openapi` (status/url); update `get_openapi` examples to the url/inline discriminated form already contracted; validate with `yaml.safe_load` + Draft 2020-12 check on each schema

## 2. Injection-hint table (single source of truth)

- [ ] 2.1 `apps/mcp-server/src/mcp_server/auth_schemes.py`: hints for all 16 schemes mirroring `proxy-plugin/internal/credential/injector.go` (incl. api_key_header/api_key_query default names + per-credential overrides, basic_auth user:pass note, vault-pregenerated token schemes, ssh_*/email_* → handled-by-other-proxy, mtls → not_implemented); cross-reference comments both ways
- [ ] 2.2 Enum-parity test: parse `AuthScheme` from vault.proto, assert every value has a table entry (and no orphan entries)

## 3. Discovery tools

- [ ] 3.1 `discover`: add `injection_hint` per service from the table; tighten `how_to_call.notes`
- [ ] 3.2 `describe_service`: add `auth_scheme_details` (table + credential header/query overrides), `your_constraints` (caller's permission_grants.constraints, nulls when unset), `explicit_proxy_url`, `openapi` status object; uniform behavior for email/ssh kinds
- [ ] 3.3 `list_services`: hint line pointing to describe_service/discover; no per-item bloat
- [ ] 3.4 `get_openapi`: implement url/inline modes per contract — etag-conditional fetch, 1 MiB cap, 10 s timeout, no off-host redirects, `not_registered`/`fetch_failed` statuses; update `services.openapi_etag` on fetch
- [ ] 3.5 `landing.py`: ensure the fresh-agent path names bootstrap as step 1 and discovery as step 2 (verify, minimal edits)

## 4. Bootstrap accuracy

- [ ] 4.1 Rewrite stale sections of `skills/agent-bootstrap.md`: describe_service fields now real; add per-scheme cheat-sheet section rendered from the auth_schemes table; document get_openapi modes; remove every promised-but-absent field
- [ ] 4.2 Bootstrap-parity test: backtick-quoted response fields promised in discovery sections must exist in the actual response models

## 5. Docs

- [ ] 5.1 `docs/HOW-TO.md` service registration: set `openapi_url` to make specs agent-discoverable; one paragraph on what agents see

## 6. Tests & verification

- [ ] 6.1 Unit tests per changed tool (field presence, constraint nulls, mtls honesty, openapi statuses, etag conditional flow with mocked httpx) — mcp-server suite (runs in CI since #213)
- [ ] 6.2 Live verification on an isolated stack: cold-start script following only on-wire hints from landing → first successful proxied call (the spec's self-serve scenario); confirm `your_constraints` matches a seeded grant
- [ ] 6.3 Full suites green; tools.yaml lint; no plaintext-gate regressions
