# Tasks — MCP Server Token-Usage Optimizations

> Atomic, one-at-a-time tasks for a Sonnet implementer. Each ≤ 200 lines of new code.
> Run commands from `apps/mcp-server/` unless noted. Repo root = `mintkey/`.
> Reference design: `.kiro/specs/mcp-token-optimization/design.md`
> Reference requirements: `.kiro/specs/mcp-token-optimization/requirements.md`
> Tooling: use `uv run` for python/pytest/mypy/ruff if the project uses uv
> (`uv run pytest ...`); otherwise the bare command. Confirm with
> `uv run python -c "print(1)"` once at the start.

> GLOBAL RULES
> - Do NOT edit any existing test file. Existing assertions are honored, not changed.
> - `agent-bootstrap.md` is sectioned by XML tags, NOT H2 headers (requirements §1.1).
> - After EVERY task: `ruff check src/mcp_server/` and the task's `mypy` line must be clean.
> - Surgical edits only — touch only the lines the task names.

---

### Task 0 — Read the OpenAPI contract once (subagent) and write notes
**Depends on:** none.
**Files (create):** `.kiro/specs/mcp-token-optimization/admin-api-client-notes.md`
**Do:**
1. Dispatch ONE subagent (general-purpose) to read, from repo root:
   - `docs/architecture/contracts/rest/openapi.yaml`
   - `apps/mcp-server/src/mcp_server/auth/agent_key.py` (to learn the real admin-api
     validate-agent-key path + request/response field names the MCP server uses today)
2. The subagent extracts and writes to the notes file:
   - The agent-key validation endpoint: exact path, method, request body field names,
     200 response field names (e.g. `agent_id`, `tenant_id`).
   - The canonical Mintkey error envelope fields consumed by
     `jsonrpc.py::_upstream_to_tool_result`: `code` / `mintkey:code`, `title`, `detail`,
     `reason_code`, `hint`.
   - The `request_token` and discovery response field names the MCP tools relay.
3. The YAML is read ONCE here and never reopened by later tasks.
**Verify:**
- `test -f .kiro/specs/mcp-token-optimization/admin-api-client-notes.md && echo NOTES_OK`
  → prints `NOTES_OK`.
- `grep -qi "validate" .kiro/specs/mcp-token-optimization/admin-api-client-notes.md && echo HAS_VALIDATE`
  → prints `HAS_VALIDATE`.
---

### Task 1 — Create the shared admin-api client module
**Depends on:** Task 0.
**Files (create):** `apps/mcp-server/src/mcp_server/admin_api_client.py`
**Do:**
1. Implement `AdminApiClient` + `AgentContext` Pydantic v2 model per design §9, filling
   `_VALIDATE_PATH` and request/response field names from `admin-api-client-notes.md`
   ONLY (not from guesswork).
2. Do NOT modify `auth/agent_key.py` behavior. If the notes show `agent_key.py` already
   makes this call, re-express the call shape here as the typed boundary; leave
   `agent_key.py` untouched.
3. Add a module docstring stating: "Single typed boundary for admin-api HTTP calls from
   the MCP server. Handler code MUST import from here, not call httpx directly."
**Verify:**
- `mypy --strict src/mcp_server/admin_api_client.py` → exit 0, `Success: no issues`.
- `ruff check src/mcp_server/admin_api_client.py` → exit 0.
- `python -c "from mcp_server.admin_api_client import AdminApiClient, AgentContext; print('CLIENT_OK')"`
  → prints `CLIENT_OK`.

> **This task creates the shared API client. All subsequent handler tasks MUST import
> from this module. Do not proceed to Task 2 until this module passes `mypy --strict`.**
---

### Task 2 — Bootstrap section parser (no handler/route change yet)
**Depends on:** Task 1.
**Files (edit):** `apps/mcp-server/src/mcp_server/tools/bootstrap.py`
**Do:**
1. Add `import re` to the imports.
2. After the existing `_VERSION = "1.0"` line, add the module-level parser blocks from
   design §3.1: `_SECTION_TAGS`, `_SECTION_NAMES`, `_RESOURCE_URI`,
   `_extract_xml_block`, `_extract_overview`, `_SECTIONS`, `_OVERVIEW`,
   `_BOOTSTRAP_VERSION`, and the import-time `assert` self-checks.
3. Add the `_bootstrap_payload(section: str | None) -> dict` function from design §3.2.
4. Do NOT change the route handler yet (Task 3 does that).
**Verify:**
- `mypy --strict src/mcp_server/tools/bootstrap.py` → exit 0.
- `ruff check src/mcp_server/tools/bootstrap.py` → exit 0.
- `python -c "from mcp_server.tools.bootstrap import _bootstrap_payload, _SECTION_NAMES; \
  p=_bootstrap_payload('index'); assert 'skill_markdown' not in p; \
  assert p['resource_uri']=='mintkey://skill/agent-bootstrap'; \
  assert p['bootstrap_version']=='2.0'; assert len(_SECTION_NAMES)==7; \
  f=_bootstrap_payload('full'); assert 'skill_markdown' in f and f['version']=='1.0'; \
  a=_bootstrap_payload('auth'); assert '<authentication>' in a['content'] and '<agent_secrets>' not in a['content']; \
  u=_bootstrap_payload('bogus'); assert 'sections' in u; print('PARSER_OK')"`
  → prints `PARSER_OK`.
---

### Task 3 — Wire `section` into the REST route
**Depends on:** Task 2.
**Files (edit):** `apps/mcp-server/src/mcp_server/tools/bootstrap.py`
**Do:**
1. Add `Query` to the FastAPI import: `from fastapi import APIRouter, Query, Request`.
2. Change the route signature + body per design §3.3:
   `async def bootstrap(request: Request, section: str | None = Query(default=None)) -> JSONResponse:`
   and `return JSONResponse(_bootstrap_payload(section))`.
3. Append one docstring line documenting `?section=` and `bootstrap_version: "2.0"`.
**Verify:**
- `mypy --strict src/mcp_server/tools/bootstrap.py` → exit 0.
- `pytest tests/test_bootstrap.py -q` → all pass (existing bootstrap tests: default route
  still 200; markdown-sections test now hits `?section=full`? NO — those tests call
  `/v1/tools/bootstrap` with no query, which now returns `index`. **Check:**
  `test_bootstrap_markdown_contains_required_sections` asserts `<authentication>` etc. in
  `skill_markdown`. With default=index there is no `skill_markdown`. This WILL fail.)
  → **STOP. This is a real conflict. Apply Task 3a before declaring Task 3 done.**
---

### Task 3a — Resolve the default-bootstrap test conflict
**Depends on:** Task 3.
**Files:** none edited in `tests/`. Decision-only + minimal handler adjustment.
**Context:** `tests/test_bootstrap.py::test_bootstrap_route_exists_and_returns_200` and
`test_bootstrap_markdown_contains_required_sections` call `GET /v1/tools/bootstrap` with
NO query and assert `skill_markdown` is present and contains XML section tags. FR-3 makes
the default `index` (no `skill_markdown`). These contradict. INV-3 forbids editing tests.
**Do — apply Decision D-2 (default stays index for the TOOL, but REST default stays full):**
The token saving that matters is on the **MCP `tools/call`** path (what models invoke),
not the raw REST route. So:
1. Keep the REST route default = **full legacy payload** (so existing REST tests pass):
   in `bootstrap.py`, when `section is None` AND the call is the REST route, return the
   legacy full payload. Implement by changing the route default to `section="full"` is
   WRONG (it would make REST default full but lose index). Instead: keep
   `_bootstrap_payload`'s `index` default, but have the **REST route** pass
   `section or "full"` so a bare `GET /v1/tools/bootstrap` yields `full` (back-compat),
   while `?section=index` yields the lean index.
   - Route line becomes: `return JSONResponse(_bootstrap_payload(section or "full"))`
2. The **MCP tool** path (Task 5) maps `mintkey_bootstrap` with no `section` arg to the
   tool default `index` by sending `?section=index` explicitly (so models get the lean
   default). Task 5 enforces this.
**Net effect:** bare REST GET = full (tests pass, back-compat). MCP tool default = index
(token saving where it counts). `?section=...` works on both.
**Verify:**
- `pytest tests/test_bootstrap.py -q` → all pass (incl. NET-B parametrized url tests and
  the markdown-sections test, because bare GET now returns full).
- `mypy --strict src/mcp_server/tools/bootstrap.py` → exit 0.
---

### Task 4 — MCP Resource registration (resources/list + resources/read)
**Depends on:** Task 3a.
**Files (edit):** `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`
**Do:**
1. Add `"resources": {"listChanged": False, "subscribe": False}` to `_CAPABILITIES`
   (design §3.6), keeping `tools` and `experimental` unchanged.
2. Add the import + `_RESOURCES` + `_handle_resources_list` + `_handle_resources_read`
   from design §3.6.
3. In `_dispatch`, add the `resources/list` and `resources/read` branches after the
   `tools/list` branch (UNauthenticated, per design §3.6 rationale).
**Verify:**
- `mypy --strict src/mcp_server/tools/jsonrpc.py` → exit 0.
- `ruff check src/mcp_server/tools/jsonrpc.py` → exit 0.
- `pytest tests/test_jsonrpc.py -q` → all existing pass.
---

### Task 5 — Tool schema: add `section`, remove `title`, send index default
**Depends on:** Task 4.
**Files (edit):** `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`
**Do:**
1. Replace the `mintkey_bootstrap` TOOLS entry with the design §3.5 "After" block
   (adds `section` enum schema; removes `title`).
2. In `_dispatch_tool`, replace the `mintkey_bootstrap` branch with the design §3.4
   "After" block, BUT default to `index` for the tool path: send
   `params["section"] = args.get("section") or "index"` so a no-arg tool call yields the
   lean index (Task 3a Decision D-2). If `mypy` flags the local `params` name colliding
   with the later `secret_list` local, rename this one `bootstrap_params`.
**Verify:**
- `mypy --strict src/mcp_server/tools/jsonrpc.py` → exit 0.
- `python -c "from mcp_server.tools.jsonrpc import TOOLS; \
  b=[t for t in TOOLS if t['name']=='mintkey_bootstrap'][0]; \
  assert 'title' not in b; assert b['inputSchema']['properties']['section']['default']=='index'; \
  print('SCHEMA_OK')"` → prints `SCHEMA_OK`.
---

### Task 6 — Trim secret descriptions + remove all remaining `title` keys
**Depends on:** Task 5.
**Files (edit):** `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`
**Do:**
1. Apply the four exact secret description replacements from design §5.2 (`secret_put`,
   `secret_get`, `secret_list`, `secret_delete`).
2. Remove the `"title": "..."` key from ALL remaining TOOLS entries
   (`mintkey_list_services`, `mintkey_discover`, `mintkey_describe_service`,
   `mintkey_get_openapi`, `mintkey_request_token`, `secret_put`, `secret_get`,
   `secret_list`, `secret_delete`). `mintkey_bootstrap` title already removed in Task 5.
3. Do NOT change any non-secret `description` text (design §5.3).
**Verify:**
- `mypy --strict src/mcp_server/tools/jsonrpc.py` → exit 0.
- `python -c "from mcp_server.tools.jsonrpc import TOOLS; \
  assert all('title' not in t for t in TOOLS); \
  d={t['name']:t['description'] for t in TOOLS}; \
  assert d['secret_put']=='Store (or overwrite) a named secret owned by the calling agent.'; \
  assert d['secret_get']=='Read the plaintext value of a secret you own or were granted read access to.'; \
  assert d['secret_list']=='List metadata for secrets you own or that are shared with you. Never returns values.'; \
  assert d['secret_delete']=='Delete a secret you own. Cascades share grants. Idempotent.'; \
  print('TRIM_OK')"` → prints `TRIM_OK`.
---

### Task 7 — Cap error hint to 120 chars
**Depends on:** Task 6.
**Files (edit):** `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`
**Do:**
1. In `_upstream_to_tool_result`, change the single line
   `parts.append(f"hint: {hint}")` → `parts.append(f"hint: {hint[:120]}")`
   (design §6). Touch nothing else in that function.
**Verify:**
- `mypy --strict src/mcp_server/tools/jsonrpc.py` → exit 0.
- `python -c "from mcp_server.tools.jsonrpc import _upstream_to_tool_result, _synthetic_error_response as E; \
  r=_upstream_to_tool_result(E(400, {'code':'x','hint':'H'*300})); \
  txt=r['content'][0]['text']; \
  import re; m=re.search(r'hint: (H+)', txt); assert m and len(m.group(1))==120, len(m.group(1) if m else ''); \
  print('HINT_CAP_OK')"` → prints `HINT_CAP_OK`.
---

### Task 8 — Replace `_BUILTIN_CAPABILITIES` (short pointer, keep required literals)
**Depends on:** Task 7.
**Files (edit):** `apps/mcp-server/src/mcp_server/tools/discovery.py`
**Do:**
1. Replace the `_BUILTIN_CAPABILITIES` constant with the design §4.1 "After" string
   (retains `secret_put/secret_get/secret_list/secret_delete` and `mintkey_get_openapi`).
2. Do NOT change the two `"capabilities": _BUILTIN_CAPABILITIES` payload lines (FR-18).
3. Do NOT change `list_services` hint logic (Decision D-1: list_services unchanged).
4. Confirm `discover` already only sets `hint` when empty (design §4.4) — if it matches
   the "Before" exactly, make NO edit to `discover`'s hint logic.
**Verify:**
- `mypy --strict src/mcp_server/tools/discovery.py` → exit 0.
- `ruff check src/mcp_server/tools/discovery.py` → exit 0.
- `pytest tests/test_discovery_dx.py -q` → ALL pass, especially
  `TestBuiltinCapabilitiesAdvertised` (constant mentions secret tools +
  `mintkey_get_openapi`; source has exactly two `"capabilities": _BUILTIN_CAPABILITIES`)
  and `TestListServicesHint` (non-empty list still has a hint).
- `python -c "from mcp_server.tools.discovery import _BUILTIN_CAPABILITIES as C; \
  assert len(C)<200; assert 'mintkey_get_openapi' in C; \
  assert all(s in C for s in ('secret_put','secret_get','secret_list','secret_delete')); \
  print('CAP_OK', len(C))"` → prints `CAP_OK` and a number < 200.
---

### Task 9 — New tests for P1/P2/P6 (additive only)
**Depends on:** Task 8.
**Files (create):** `tests/test_bootstrap_sections.py`, `tests/test_mcp_resources.py`,
`tests/test_tools_list_trim.py`, `tests/test_error_hint_cap.py`
**Do:** Implement the test cases enumerated in design §7 (T-A, T-B, T-C, T-D). Reuse the
ASGI-loopback + `validate_agent_key` monkeypatch harness from `tests/test_bootstrap.py`
(copy it into each new file; do not import private helpers across modules). For
`tools/call` and `resources/*` JSON-RPC tests, POST the JSON-RPC envelope to `/mcp` with
header `Authorization: Bearer mk_agent_test` where auth is required; `resources/*` are
unauthenticated so no header is needed for T-B.
**Verify:**
- `pytest tests/test_bootstrap_sections.py tests/test_mcp_resources.py tests/test_tools_list_trim.py tests/test_error_hint_cap.py -q`
  → all pass, exit 0.
---

### Task 10 — Full regression + lint/type gate (final)
**Depends on:** Task 9.
**Files:** none (verification only).
**Do:** Run the complete gate. If anything fails, fix the offending earlier task's edit
(do NOT edit existing tests; if an existing test genuinely contradicts a requirement,
STOP and escalate per CLAUDE.md — do not silently weaken the test).
**Verify (all must pass, capture exit codes):**
- `ruff check src/mcp_server/` → exit 0.
- `mypy --strict src/mcp_server/admin_api_client.py src/mcp_server/tools/bootstrap.py src/mcp_server/tools/discovery.py src/mcp_server/tools/jsonrpc.py`
  → exit 0, `Success: no issues`.
- `pytest tests/ -q` → exit 0; report the passed/failed/skipped counts from the runner
  output (per CLAUDE.md Principle 1 — show the numbers, do not claim "tests pass").
- Final sanity: bare `GET /v1/tools/bootstrap` returns full payload (back-compat);
  `mintkey_bootstrap` tool with no args returns index (lean). Demonstrate with a short
  ASGI snippet and paste the two response shapes.
---

## Task dependency graph (strict linear order)

```
0 → 1 → 2 → 3 → 3a → 4 → 5 → 6 → 7 → 8 → 9 → 10
```

Each task ≤ 200 lines new/changed code. Task 10 is the regression proof that nothing
broke. Do not parallelize — later tasks edit the same files (`jsonrpc.py`) as earlier
ones.
