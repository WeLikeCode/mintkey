# Mintkey docs — syntax + Kiro/SDD readiness review

Run on 2026-05-10. Tooling: `mermaid-cli@10.9.1` (via `npx -p @mermaid-js/mermaid-cli@10`), `openapi-spec-validator` 3.x + `@redocly/cli`, Python `jsonschema` Draft 2020-12 validator, `protoc 34.1` (Homebrew protobuf).

Scope counted before validation: 16 accepted ADRs (0001–0016), 6 iteration-4 contract artefacts under `docs/contracts/` (`rest/openapi.yaml`, `mcp/tools.yaml`, `events/audit-event.schema.json`, `events/change-event.schema.json`, `events/span-attributes.md`, `vault-adapter/vault.proto`), and 7 iteration-3 flows under `docs/03-flows/` (`F-OP-01..04`, `F-AG-01..02`, `E2E-01`). All counts match the working tree.

## 1. Mermaid blocks — 33 total, 25 passing

Discovery: `grep -rn '\`\`\`mermaid' README.md docs/` → 33 fenced blocks across 17 files. Each block was extracted to `block_<idx>.mmd` and rendered with `mmdc -i <input> -o /tmp/check.svg`. Eight blocks fail to parse. **All 8 failures live in `docs/03-flows/` and `docs/00-vision/07-kiro-readiness.md`** — every other diagram (proposals, architecture views, observability, deployment, vision/roadmap, F-OP-01, the E2E walkthrough's nine diagrams) renders cleanly.

### FAILs (listed first; all eight)

- **`docs/00-vision/07-kiro-readiness.md:9` — FAIL: identifier `style` collides with the Mermaid flowchart `style` keyword.** Inside `subgraph LIB["4-7. Reusable libraries"]` the node is declared `style["Coding conventions"]`. The parser hits `style` and expects `style <node> <css>` syntax, then sees `[` and emits `Expecting 'SPACE', got 'SQS'` at the bracket. Rename the node id (e.g. `styleguide["Coding conventions"]`).
- **`docs/03-flows/F-AG-01-discover-and-request-token.md:24` — FAIL: semicolon inside sequence-message text.** Line 32 of the doc, line 8 of the block: `MCP->>MCP: parse Bearer; format check (mk_agent_ prefix)`. Mermaid's sequenceDiagram parser treats `;` as a statement terminator inside message text; the rest of the line then bombs as a fresh statement starting with `format check (...)`. Replace `;` with `,` or `—`.
- **`docs/03-flows/F-AG-01-discover-and-request-token.md:47` — FAIL: same pattern.** Block line 20: `Br->>Bus: (no-op for issuance; revocation only on the bus)`. Drop or replace the `;`.
- **`docs/03-flows/F-AG-02-brokered-call-happy-path.md:29` — FAIL: same pattern, twice.** Block line 18: `check jti not in revocation set; agent not in revoked-agent set`. Block line 28 also chains semicolons inside `Plg->>Plg:` (`response scrubber: strip Authorization, Cookie, Set-Cookie if present; scan body for known credential fingerprint (defense in depth)`). Both must lose the `;`.
- **`docs/03-flows/F-OP-02-register-service.md:24` — FAIL: same pattern.** Block line 27 (doc line 50): `Kos->>Kong: POST /config (declarative YAML; new route for the service)`.
- **`docs/03-flows/F-OP-03-register-credential-and-test.md:22` — FAIL: same pattern.** Block line 21 (last line, in the `UI-->>Op:` message): `success; credential row appears with key_version`.
- **`docs/03-flows/F-OP-03-register-credential-and-test.md:48` — FAIL: same pattern.** Block line 11: `API->>API: RBAC; rate limit per service (e.g., 10/min)`. After `;` ends the message, the parser sees `rate limit per service (e.g., 10/min)` as a new statement and trips on the comma inside `(e.g., 10/min)`. Replace `;` with `,` (or move the `(e.g., 10/min)` into a `Note over API`).
- **`docs/03-flows/F-OP-04-create-agent-and-permissions.md:25` — FAIL: raw `<…>` placeholder treated as HTML.** Block line 12: `API->>API: generate 32 random bytes; format mk_agent_<base32-26>`. Two problems on one line: a semicolon (covered above) and the `<base32-26>` token, which Mermaid hands off to its HTML allowlist; `base32-26` is not in `{br, b, i, em, strong, u}` so the lexer emits `INVALID`. Use `mk_agent_…(base32-26)` or HTML-escape (`&lt;base32-26&gt;`).

### PASSes (25)

- `docs/00-vision/06-roadmap.md:25` — OK
- `docs/01-architecture/01-system-context.md:7` — OK
- `docs/01-architecture/02-container-view.md:17` — OK
- `docs/01-architecture/03-quality-attributes.md:10` — OK
- `docs/01-architecture/05-threat-model.md:10` — OK
- `docs/03-flows/E2E-01-builder-happy-path.md:34, :48, :75, :98, :125, :159, :205, :235, :269` — OK (nine diagrams, all clean)
- `docs/03-flows/F-OP-01-bootstrap-and-login.md:29, :65` — OK
- `docs/03-flows/F-OP-04-create-agent-and-permissions.md:49` — OK (the *second* diagram in this file is fine; it's only the first that breaks)
- `docs/04-observability/README.md:7` — OK
- `docs/05-deployment/README.md:11` — OK
- `docs/proposal/P-005-egress-proxy-implementation.md:152, :172, :199` — OK
- `docs/proposal/P-006-admin-tech-stack-and-auth.md:232, :266` — OK
- `docs/proposal/P-007-multi-tenancy.md:78` — OK

The pattern is uniform: every flow that introduces a new sequence diagram inherited a `;`-as-aside habit ("X; Y", "(A; B)"). E2E-01 escaped this because its messages tend to use commas and parentheses without inline semicolons; the F-* flows didn't.

## 2. OpenAPI — PASS (Spec 3.1.0 strict) / FAIL (Redocly: 21 errors, 20 warnings)

Two validators were run against `docs/contracts/rest/openapi.yaml`.

- `openapi_spec_validator.openapi_v31_spec_validator.iter_errors(...)` → **0 errors**. Schema is structurally valid OpenAPI 3.1.
- `npx @redocly/cli@latest lint --format=stylish` → **21 errors, 20 warnings**.

The 21 Redocly errors are **all the same root cause**: `nullable: true` is a 3.0 keyword that was removed from OAS 3.1 in favour of `type: [string, null]` / `oneOf: [..., {type: null}]`. The document declares `openapi: 3.1.0` but uses 3.0 nullability. Affected lines (every one is `nullable: true`):

`1905, 2025, 2073, 2093, 2104, 2133, 2142, 2253, 2284, 2316, 2361, 2488, 2491, 2495, 2499, 2526, 2559, 2574, 2599, 2602, 2681`.

Fix is mechanical — replace each `type: <T>` + `nullable: true` pair with `type: [<T>, "null"]` (or `oneOf` for $ref'd types). `openapi-spec-validator` is lenient and didn't catch this; Redocly is stricter and is correct.

The 20 warnings break into four buckets:

1. **Operations missing 4XX response (5 ops)** at lines 162, 197, 278, 1342, 1364, 1411 — these are: `authLoginRedirect`, `authLoginCallback`, `authLogout`, `health`, `ready`, `jwks`. Auth + health + JWKS endpoints arguably don't *need* application 4xx documentation; Redocly suggests adding them anyway.
2. **Operations missing 2XX response (2 ops)** at lines 162, 197 — same auth-redirect ops; they only return 302/503 today. The 302 is technically the success code, so this is a false positive once you treat 3xx as success.
3. **Example value does not match schema (8 hits)** — the `auth/me` and `auth/callback` examples (lines 252, 257, 311, 1396) reference an `active_tenant` that omits `status`, `settings`, `created_at`, `updated_at` and an email example that doesn't match `format: email`. This is a real bug: the examples need to be expanded to satisfy `required` on the `Tenant` schema, or the schema should mark those fields optional.
4. **Unused components (2 hits)** — `Session` (line 2579) and `UlidId` (line 1827) are defined but never `$ref`-ed. `UlidId` is documented as the canonical type for ULIDs but the actual responses inline `type: string + pattern`. `Session` shows up in the API tag table and the `OperatorSession` security scheme reference, but the *schema* component itself is unused. Either reference these from concrete responses or delete them.
5. **Server URL** at line 79 — `http://localhost:8000` triggers `no-server-example.com`; cosmetic.

So: spec is **structurally valid OpenAPI 3.1**, but uses dialectally-wrong `nullable` and has ~10 example/coverage gaps that should be cleaned up.

## 3. JSON Schema — PASS / PASS

`Draft202012Validator.check_schema(...)`:

- `docs/contracts/events/audit-event.schema.json` — **PASS**. Meta-schema valid. 23 event variants under `oneOf`, each `allOf`-extends `envelope`, each pinning `event_type` and `target_type` as `const`. Discriminator mapping covers all 23.
- `docs/contracts/events/change-event.schema.json` — **PASS**. 7 event variants, discriminator mapping covers all of them, four worked examples at the bottom.

Both files load and pass meta-schema validation. (Description-level gaps are reported under §5.3 below.)

## 4. Proto — PASS

`protoc --proto_path=docs/contracts/vault-adapter --descriptor_set_out=/dev/null docs/contracts/vault-adapter/vault.proto` exits 0 with no warnings. Proto3 syntax, every message has typed fields, every service RPC has request/response types defined. Clean.

## 5. Kiro / SDD readiness findings

### 5.1 OpenAPI examples per non-trivial response — 1 issue

After resolving `$ref`'d responses (most error responses are `$ref: "#/components/responses/BadRequest"` etc., and those `responses` definitions carry their own `application/problem+json` `example`), every operation × response code with a body either has an example (200/201/4xx/5xx via shared `responses/*` components) or carries `204 No Content` (no body). Concretely the 35 operations × all their response codes were walked, and **0 missing examples** were found once `$ref` traversal is honoured. Note the eight Redocly example-conformance warnings called out in §2 — those are **examples that exist but don't match the schema**, which is a separate (and more serious) defect than missing examples; flag for triage.

### 5.2 MCP tools — request and response examples — 0 issues

All 5 tools (`list_services`, `describe_service`, `get_openapi`, `request_token`, `proxy_endpoint`) carry an `examples:` array with at least one `{request, response}` pair; `get_openapi` carries two (one per `oneOf` arm). Clean.

### 5.3 JSON Schema field descriptions — 133 missing descriptions

The audit-event schema has **123 fields without `description`** and the change-event schema has **10**. The vast majority (≈ 100 of 123) are the per-event-type discriminator props `event_type`/`target_type` (declared as `{ "const": "tenant.created" }` etc.) and the `payload` wrapper itself — these are arguably self-documenting via the `const` value or the parent schema's `description`, but the user-stated rule is "every JSON Schema field has a description", so they count. The ~30 *substantive* gaps are payload properties carrying real semantic weight without docs:

- audit-event: `ev_tenant_created.payload.{slug, display_name, isolation_mode}`, `ev_tenant_updated.payload.fields_changed`, `ev_tenant_deleted.payload.reason`, `ev_operator_created.payload.{username, email, platform_admin}`, `ev_operator_permission_*.payload.role`, `ev_service_registered.payload.{name, base_url, actions}`, `ev_service_updated.payload.fields_changed`, `ev_service_removed.payload.reason`, `ev_credential_registered.payload.key_version`, `ev_credential_rotated.payload.{key_version, previous_key_version}`, `ev_credential_revoked.payload.{key_version, reason}`, `ev_agent_created.payload.name`, `ev_agent_revoked.payload.reason`, `ev_agent_permission_granted.payload.{action, constraints}`, `ev_agent_permission_revoked.payload.action`, `ev_token_issued.payload.{scope, ttl_seconds, key_version}`, `ev_token_denied.payload.{scope, reason_code}`, `ev_proxy_hit.payload.{request_method, status_code, latency_ms, outcome}`, `ev_proxy_denied.payload.reason_code`, `ev_proxy_error.payload.{error_kind, status_code}`, `ev_kek_rotated.payload.{kek_version_from, kek_version_to, rewrapped_dek_count}`, `ev_auth_login_*.payload.{method, ip, user_agent, reason_code}`.
- change-event: `ev_credential_rotated.key_version`, `ev_credential_revoked.key_version` (the rest are `event_type` `const` discriminators).

Recommend adding one-line descriptions on every payload property; for the `event_type` consts, a single `description` on the const sufficiently documents the discriminator.

### 5.4 TODO / TBD / [unclear] / XXX markers in `docs/contracts/` and `docs/03-flows/` — 0 found

`grep -rn -E '\b(TODO|TBD|XXX|FIXME|\[unclear\])\b' docs/contracts/ docs/03-flows/` returned no hits. Clean.

### 5.5 Stable `mintkey:code` for non-2xx responses — 0 issues

Every non-2xx response in OpenAPI carries an example whose `mintkey:code` value matches `^[a-z][a-z0-9_]*$` (snake_case identifier). 10 distinct `mintkey:code` strings were found across the spec; all are stable identifiers (e.g. `validation_failed`, `not_authorized`, `tenant_suspended`, `agent_revoked`, `tenant_deleted`). No free-form English strings or sentence-case codes detected.

### 5.6 Test plan coverage (unit + integration + live-smoke) — 0 issues

All 7 flow docs (`F-OP-01..04`, `F-AG-01..02`, `E2E-01`) name **unit tests, integration tests** (most reference testcontainers), and **live-smoke** explicitly. F-AG-01..02 and the F-OP series each route their live-smoke through E2E-01's 7-phase walkthrough; E2E-01 itself owns the headline live-smoke plan. No flow is missing a test bucket.

### 5.7 Kiro spec inputs sections (components + contracts + sequenced TDD tasks) — 1 gap

Of the 7 flows, 6 explicitly name **components**, **contracts touched**, and **sequenced TDD tasks**. The exception:

- **`F-OP-01-bootstrap-and-login.md`** — the "Kiro spec inputs" section names components (`seed-job`, `admin-api`, `admin-ui`) and a 9-step TDD task list, but does **not** name the **contracts touched**. ADR references appear under "Design", but no OpenAPI operation IDs (`authLoginRedirect`, `authLoginCallback`, `authLogout`, `authMe`, internal-login endpoints) or schema files are named. Suggest a one-line "Contracts touched:" entry pointing at the auth section of `openapi.yaml` and at the auth-related audit events (`auth.login_success`, `auth.login_failed`, `auth.logout`).

The other six flows include explicit "Contracts" lines:
- F-AG-01: MCP tools + JWT shape (ADR-0006/0008).
- F-AG-02: JWT shape, JWKS, vault-adapter `GetCredential` RPC, `proxy.hit` audit event.
- F-OP-02: `POST /v1/tenants/{tid}/services` + `service.registered` change event + `service.registered` audit event.
- F-OP-03: `POST .../credentials`, `POST .../test`, vault `PutCredential`, `credential.registered` audit event.
- F-OP-04: `POST .../agents`, `POST .../permissions`, `agent.created` and `permission.granted` audit events.
- E2E-01: enumerates every contract touched, phase-by-phase.

### 5.8 Cross-file `$ref` consistency — 2 orphan schemas + a separate inline-vs-$ref check

Component-schema `$ref` analysis on the OpenAPI document:

- **Orphan schemas (defined, never referenced)**: 2 — `#/components/schemas/UlidId` (line 1827) and `#/components/schemas/Session` (line 2579). Either reference them or delete them. `UlidId` is the bigger smell: the spec defines a canonical "ULID with prefix" string type but every concrete property inlines `type: string` + a per-prefix `pattern` instead of `$ref`-ing `UlidId`. If `UlidId` is meant to be the canonical primitive, replace those 30+ inline patterns with `$ref`. If not, delete the component.
- **Inlined-as-defined-component duplicates**: 0 detected. Walking every embedded `type: object` schema and matching property-name signatures against defined schemas produced no collisions, so concrete domain shapes are not being inadvertently inlined twice. Good.

`docs/contracts/mcp/tools.yaml` uses internal `$defs/*` consistently for all repeated shapes (`service_id`, `agent_id`, `auth_scheme`, `service_summary`, `service_full`, `error_code`, `timestamp`); no inlined duplicates there.

The two event schemas use internal `$defs` consistently as well; no cross-file `$ref`s into `openapi.yaml` (intentional — the event schemas are independent JSON Schema artefacts shipped alongside the OpenAPI doc).

---

## Summary scoreboard

| Check | Result |
|---|---|
| Mermaid render (33 blocks) | **25 PASS / 8 FAIL** |
| OpenAPI 3.1 structural validity | **PASS** |
| OpenAPI Redocly lint | **21 errors / 20 warnings** (all 21 errors = `nullable` 3.0→3.1 migration) |
| `audit-event.schema.json` meta-schema | **PASS** |
| `change-event.schema.json` meta-schema | **PASS** |
| `vault.proto` protoc compile | **PASS** |
| Examples per non-trivial OpenAPI response | **0 missing** |
| MCP tool req/resp examples | **0 missing** |
| JSON Schema description coverage | **133 fields lack `description`** (≈ 30 substantive) |
| TODO / TBD / [unclear] / XXX markers | **0** |
| Stable `mintkey:code` for non-2xx | **0 free-form** |
| Flow Test plan (unit/integration/live-smoke) | **7/7 cover all three** |
| Flow Kiro spec inputs (components + contracts + TDD tasks) | **6/7 complete; F-OP-01 lacks contracts list** |
| Cross-file `$ref` consistency | **2 orphan schemas, 0 inline-duplicate collisions** |

### Recommended fix order

1. **Mermaid — global** (priority 1). Forbid `;` inside sequence-diagram message text in the contributor guide; rename `style` flowchart node in `07-kiro-readiness.md`; HTML-escape or rewrite `<base32-26>` in `F-OP-04`. Eight blocks → eight one-line fixes.
2. **OpenAPI — `nullable: true`** (priority 1). Mechanical sed over 21 lines: `nullable: true` ⇒ `type: [<orig>, "null"]`. Re-run Redocly to confirm the error count drops to 0.
3. **JSON Schema descriptions** (priority 2). Add `description` to the ~30 substantive payload properties; either add per-const descriptions or accept that the discriminator value is self-documenting.
4. **OpenAPI orphan schemas** (priority 2). Either wire `UlidId` into all ULID props (preferred, since the spec already documents it as canonical) or delete `UlidId` + `Session`.
5. **OpenAPI example/schema mismatches** (priority 2). Fix the 4 `active_tenant` example responses to satisfy `required` on `Tenant`, and update the `email` example to match `format: email`.
6. **F-OP-01 Kiro spec inputs** (priority 3). Add a "Contracts touched" line.
7. **OpenAPI 4XX/2XX coverage warnings** (priority 3, evaluate): decide per-op whether the auth-redirect / health / JWKS endpoints should declare 4xx; if not, suppress the rule with a Redocly ignore.
