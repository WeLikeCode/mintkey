# Requirements — MCP Server Token-Usage Optimizations

> Kiro spec for reducing the per-call token footprint of the Mintkey MCP server's
> tool surface (bootstrap payload, tools/list descriptions, discovery capabilities,
> error hints) WITHOUT changing any behavioral contract or breaking existing tests.
> Status: Draft.
> Authoritative constraints read from (verbatim, during spec authoring):
> - `apps/mcp-server/src/mcp_server/tools/jsonrpc.py` (TOOLS list, `_INSTRUCTIONS`, `_upstream_to_tool_result`)
> - `apps/mcp-server/src/mcp_server/tools/discovery.py` (`_BUILTIN_CAPABILITIES`, list_services/discover handlers)
> - `apps/mcp-server/src/mcp_server/tools/bootstrap.py` (bootstrap handler, `_SKILL_MARKDOWN`)
> - `apps/mcp-server/src/mcp_server/tools/request_token.py` (request_token handler)
> - `apps/mcp-server/src/mcp_server/main.py` (app factory, router registration, auth bypass list)
> - `apps/mcp-server/skills/agent-bootstrap.md` (XML-tagged sections — see §1.1)
> - `apps/mcp-server/tests/test_bootstrap.py`, `tests/test_discovery_dx.py` (existing assertions that constrain the change)
> - `docs/architecture/contracts/rest/openapi.yaml` (canonical REST contract — read ONCE in Task 0)
> - CLAUDE.md guardrails (ADR-0009 tech stack; Principle 1 verify-with-tools; Simplicity First)

---

## 1. Summary

The MCP server emits a large, repetitive token payload on common agent operations:

- `mintkey_bootstrap` returns the **entire** `agent-bootstrap.md` skill (38,850 bytes ≈ ~9,400 tokens) on **every** call, even when the agent only needs one section.
- `tools/list` ships verbose `description` strings plus a `title` field on all 10 tool entries.
- `list_services` / `discover` ship a 474-char `_BUILTIN_CAPABILITIES` blob plus a verbose `hint` on every call, including when services are present.
- Upstream tool errors inline an unbounded `hint` string into the error text block.

This spec makes four surgical, backward-compatible reductions:

1. **P1 — Bootstrap sectioning + MCP Resource.** Add an optional `section` parameter
   (`index|auth|discover|proxy_call|email|secrets|full`, default `index`) to
   `mintkey_bootstrap`; register the full skill as an MCP Resource
   (`mintkey://skill/agent-bootstrap`) so clients can fetch it out-of-band. Default
   response becomes a ~300-token table-of-contents + resource pointer.
   `section:"full"` restores today's exact payload.
2. **P2 — Trim `tools/list`.** Shorten the four `secret_*` descriptions; remove all
   `title` keys from the 10 `TOOLS` entries. Do NOT touch the other six descriptions.
3. **P3 — Pointer-ize discovery.** Replace `_BUILTIN_CAPABILITIES` with a short
   pointer string; omit the `hint` field from list_services/discover when services
   are present (emit it only when the service list is empty).
4. **P6 — Cap error hints.** Truncate the `hint` portion of upstream error text
   blocks to 120 chars.

### 1.1 Critical structural finding (governs P1 design)

`agent-bootstrap.md` is **NOT** sectioned by Markdown H2 (`##`) headers. `grep -nE '^## '`
returns exactly one H2 (`## Discovery URLs (for clients)`). The document's real,
deterministic section structure is **XML-tagged blocks** (the file's own opening
sentence: *"sections are wrapped in unambiguous XML-tagged blocks so any reasoning
system can parse them deterministically"*). Verified tag offsets:

| XML tag | lines | maps to `section` value |
|---|---|---|
| `<overview>` … `</overview>` | 13–33 | (part of `index`) |
| `<authentication>` … `</authentication>` | 62–103 | `auth` |
| `<service_discovery>` … `</service_discovery>` | 105–233 | `discover` |
| `<proxy_usage>` … `</proxy_usage>` | 235–300 | `proxy_call` |
| `<email_services>` … `</email_services>` | 359–536 | `email` |
| `<agent_secrets>` … `</agent_secrets>` | 538–610 | `secrets` |

Therefore the P1 parser MUST split by XML tags, not by H2 headers. This is an
intentional deviation from the original optimization note (which said "parse by H2
headers"); the deviation is forced by the actual file structure and is recorded here
so the implementer follows reality, not the note.

### 1.2 Critical test-coupling finding (governs P3 design)

`tests/test_discovery_dx.py::TestBuiltinCapabilitiesAdvertised` pins
`_BUILTIN_CAPABILITIES` content and shape:

- `test_constant_mentions_secret_tools` asserts the constant contains all of
  `secret_put`, `secret_get`, `secret_list`, `secret_delete`, **and** the literal
  `mintkey_get_openapi`.
- `test_list_services_and_discover_payloads_carry_capabilities` asserts the source of
  `discovery.py` contains the literal `'"capabilities": _BUILTIN_CAPABILITIES'`
  **exactly twice**.

The original optimization note's proposed replacement string drops `mintkey_get_openapi`
and would FAIL `test_constant_mentions_secret_tools`. The P3 replacement string in this
spec (design §4) is therefore adjusted to retain `mintkey_get_openapi`, and the two
`"capabilities": _BUILTIN_CAPABILITIES` assignments are retained verbatim so the
source-count assertion still passes. No test file is modified by this spec.

---

## 2. User stories (US-N format)

- **US-1.** As an AI agent that already knows how to authenticate, I call
  `mintkey_bootstrap` and want a small table-of-contents back, not 9,400 tokens of
  onboarding prose, so I can pull only the section I need.
- **US-2.** As an MCP client (Claude Code, Cursor), I want the full bootstrap skill
  available as an MCP **Resource** I can fetch on demand, so the skill text never has
  to flow through model reasoning context unless I ask for it.
- **US-3.** As an existing integration that depends on the full skill markdown in the
  bootstrap response, I want a way (`section:"full"`) to get today's exact payload, so
  I am not broken by the optimization.
- **US-4.** As an agent listing tools, I want concise tool descriptions and no
  redundant `title` fields, so `tools/list` costs fewer tokens without losing
  load-bearing guidance.
- **US-5.** As an agent re-running `discover`, I want a short capability pointer and no
  redundant per-call hint when I already have services, so the discovery response is
  lean while still teaching me about built-in tools.
- **US-6.** As an agent that hits an upstream error, I want a bounded, readable error
  line so a pathological upstream `hint` cannot blow up my context.

---

## 3. Functional requirements (FR-N table)

| ID | Requirement |
|---|---|
| FR-1 | `mintkey_bootstrap` accepts an optional `section` argument. Allowed values: `index`, `auth`, `discover`, `proxy_call`, `email`, `secrets`, `full`. Default (absent/None/empty) = `index`. |
| FR-2 | The bootstrap tool input schema in `jsonrpc.py::TOOLS` declares `section` as `{"type":"string","enum":[...7 values...],"default":"index"}`; `additionalProperties` stays `false`; `section` is NOT in `required`. |
| FR-3 | `section:"index"` returns `{ sections: [...7 names...], resource_uri: "mintkey://skill/agent-bootstrap", overview: <overview-block-text>, proxy_url, mcp_url, bootstrap_version: "2.0" }` and MUST NOT include `skill_markdown`. |
| FR-4 | `section:"full"` returns today's exact keys (`skill_markdown`, `proxy_url`, `mcp_url`, `version`) with `skill_markdown` == the verbatim full file, PLUS `bootstrap_version: "2.0"`. The pre-existing `version: "1.0"` key is retained for backward compat. |
| FR-5 | A named section (`auth`/`discover`/`proxy_call`/`email`/`secrets`) returns `{ section: <name>, content: <that XML block, tags included>, resource_uri, bootstrap_version: "2.0" }` and MUST NOT include the full `skill_markdown`. |
| FR-6 | An unrecognized `section` value returns the `index` payload (graceful fallback; never an error). |
| FR-7 | The full skill is registered as an MCP Resource with URI `mintkey://skill/agent-bootstrap`, name `agent-bootstrap`, mimeType `text/markdown`, via the MCP `resources/list` + `resources/read` JSON-RPC methods on the existing dispatcher. `resources/read` of that URI returns the verbatim file contents. |
| FR-8 | The REST route `GET /v1/tools/bootstrap` continues to accept an optional `?section=` query parameter with the same semantics as FR-1–FR-6; with no query param it returns the `index` payload. |
| FR-9 | Section parsing reads from the SAME module-level `_SKILL_MARKDOWN` already loaded at import; no second file read is added. Parsing happens once at import into a module-level `dict[str,str]`. |
| FR-10 | `tools/list` `secret_put` description == `"Store (or overwrite) a named secret owned by the calling agent."` |
| FR-11 | `tools/list` `secret_get` description == `"Read the plaintext value of a secret you own or were granted read access to."` |
| FR-12 | `tools/list` `secret_list` description == `"List metadata for secrets you own or that are shared with you. Never returns values."` |
| FR-13 | `tools/list` `secret_delete` description == `"Delete a secret you own. Cascades share grants. Idempotent."` |
| FR-14 | Every entry in `TOOLS` (all 10) has NO `title` key. |
| FR-15 | Descriptions for `mintkey_bootstrap`, `mintkey_list_services`, `mintkey_discover`, `mintkey_describe_service`, `mintkey_get_openapi`, `mintkey_request_token` are unchanged EXCEPT `mintkey_bootstrap` may add a clause documenting the new `section` param (design §3). |
| FR-16 | `_BUILTIN_CAPABILITIES` is replaced with the short pointer string in design §4 — which retains the literals `secret_put`, `secret_get`, `secret_list`, `secret_delete`, and `mintkey_get_openapi`. |
| FR-17 | In `list_services` and `discover`, the `hint` field is emitted ONLY when `all_services` is empty. When services are present, the response dict MUST NOT contain a `hint` key. |
| FR-18 | Both `list_services` and `discover` payload constructions retain the literal source line `"capabilities": _BUILTIN_CAPABILITIES` (two occurrences total in `discovery.py`). |
| FR-19 | `_upstream_to_tool_result` truncates the `hint` portion to at most 120 characters before appending it to the error text, formatted exactly as `hint: {hint[:120]}`. All other error parts (`HTTP {status}`, `code=`, title, detail, `reason=`) are unchanged. |
| FR-20 | A single typed admin-api HTTP client module (`admin_api_client.py`) is created in Task 1 and is the ONLY place raw `httpx` calls to the admin-api are made from handler code introduced or modified by this spec. (See NFR-6 for scope.) |

---

## 4. Non-functional requirements (NFR-N table)

| ID | Requirement |
|---|---|
| NFR-1 | Stack unchanged (ADR-0009): Python 3.12, FastAPI, Pydantic v2, async, structlog, ruff, `mypy --strict`, uv. No new runtime dependency beyond what `apps/mcp-server/pyproject.toml` already declares (`httpx>=0.27`, pydantic, fastapi). |
| NFR-2 | `mypy --strict` passes on every new/modified module (`admin_api_client.py`, `bootstrap.py`, `discovery.py`, `jsonrpc.py`). |
| NFR-3 | `ruff check` passes on every new/modified module. |
| NFR-4 | No existing test is modified or deleted. The full `apps/mcp-server` unit-test suite passes after every task (regression gate). |
| NFR-5 | No plaintext credential, agent key, or token is logged or placed in a span attribute by any new code (CLAUDE.md S-SEC-1 / ADR-0017.6). The bootstrap markdown contains no secrets; section text is safe to return. |
| NFR-6 | The OpenAPI contract is read EXACTLY ONCE (Task 0 subagent) and its findings written to `admin-api-client-notes.md`. The shared client (`admin_api_client.py`) is coded ONCE from those notes (Task 1) and only imported thereafter — never re-read, never re-coded. NOTE: the discovery/token handlers query the DB directly today via `get_db_session`; the shared client wraps only the admin-api calls those handlers genuinely make over HTTP (today: `validate-agent-key` via `mcp_server.auth.agent_key`). The client is the single typed boundary for any admin-api HTTP call introduced by this spec. |
| NFR-7 | Per-call token savings targets (informational, not gated by a token meter): P1 ≈ 9,400 tokens on default bootstrap; P2 ≈ 300 tokens/list; P3 ≈ 150–200 tokens/discovery call; P6 ≈ 30–60 tokens/error. |
| NFR-8 | Backward compatibility: `section:"full"` and `?section=full` reproduce today's `mintkey_bootstrap` response byte-for-byte for `skill_markdown`, `proxy_url`, `mcp_url`, `version`. |

---

## 5. Out of scope

- Rewriting `agent-bootstrap.md` content or re-sectioning it with H2 headers.
- Changing the DB-direct query pattern of discovery/request_token handlers to route
  through admin-api (they hit the DB via `get_db_session` today; that stays).
- Modifying the canonical `docs/architecture/contracts/rest/openapi.yaml`.
- Adding new MCP tools or new audit event types.
- Email/secret handler business logic.
- Any change to broker, proxy, vault, or admin-api source.
- Editing existing test files (assertions are honored, not changed).

---

## 6. Acceptance criteria (AC-N, mechanically verifiable)

All commands run from `apps/mcp-server/` unless noted.

| ID | Criterion | Verify command → expected |
|---|---|---|
| AC-1 | `section=index` default omits full skill. | `python -c "import asyncio,httpx; ..."` (design §7 test T-A) prints `index_ok` and exit 0. |
| AC-2 | `section=full` restores full payload. | Test `test_bootstrap_section_full_matches_legacy` PASSES. |
| AC-3 | Named section returns only that XML block. | Test `test_bootstrap_section_auth_returns_only_auth` PASSES (content contains `<authentication>`, not `<agent_secrets>`). |
| AC-4 | Unknown section falls back to index. | Test `test_bootstrap_unknown_section_is_index` PASSES. |
| AC-5 | MCP Resource is discoverable + readable. | `resources/list` includes `mintkey://skill/agent-bootstrap`; `resources/read` returns full file. Test `test_resources_list_and_read` PASSES. |
| AC-6 | `tools/list` has no `title` keys and trimmed secret descriptions. | `pytest tests/test_jsonrpc.py -q` PASSES; new `test_tools_list_no_titles_and_trimmed_descriptions` PASSES. |
| AC-7 | `_BUILTIN_CAPABILITIES` short + retains required literals. | `pytest tests/test_discovery_dx.py::TestBuiltinCapabilitiesAdvertised -q` PASSES (unchanged test file). |
| AC-8 | discover/list_services omit `hint` when services present, include it when empty. | New `test_hint_omitted_when_services_present` + existing `TestListServicesHint` PASS. |
| AC-9 | Error hint capped at 120 chars. | New `test_error_hint_truncated_to_120` PASSES. |
| AC-10 | `admin_api_client.py` exists and is the single typed admin-api HTTP boundary. | `mypy --strict src/mcp_server/admin_api_client.py` exit 0; grep shows handler code imports it. |
| AC-11 | Full regression: nothing broke. | `pytest tests/ -q` exit 0 (all collected unit tests pass). |
| AC-12 | Lint + types clean. | `ruff check src/mcp_server/` exit 0 AND `mypy --strict src/mcp_server/tools/bootstrap.py src/mcp_server/tools/discovery.py src/mcp_server/tools/jsonrpc.py src/mcp_server/admin_api_client.py` exit 0. |
