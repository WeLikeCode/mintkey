# Design — MCP Server Token-Usage Optimizations

> Implementation design. Self-contained: every external constraint quoted inline.
> Reference spec: `.kiro/specs/mcp-token-optimization/requirements.md`.
> All paths are relative to repo root `mintkey/`. Code lives under
> `apps/mcp-server/src/mcp_server/`.

---

## 1. Overview + key invariants

Four surgical reductions, each independently testable. Strict ordering: the shared
admin-api client (Task 1) lands before any handler edit so that all handler changes
share one typed boundary and the OpenAPI contract is read exactly once.

**Hard invariants (do not violate):**

- **INV-1 — One OpenAPI read.** `docs/architecture/contracts/rest/openapi.yaml` is read
  ONCE by the Task-0 subagent; its findings are persisted to
  `.kiro/specs/mcp-token-optimization/admin-api-client-notes.md`. No later task re-opens
  the YAML.
- **INV-2 — One client module.** `apps/mcp-server/src/mcp_server/admin_api_client.py` is
  the single typed async httpx boundary for admin-api HTTP calls touched by this spec.
  **Implementers MUST NOT make raw httpx calls to the admin-api in handler code; use
  `admin_api_client.py` exclusively.** (Scope note: discovery/request_token handlers
  query Postgres directly via `get_db_session` today and continue to; that DB path is
  not an admin-api HTTP call and is unchanged. The only admin-api HTTP call in the
  current MCP server is agent-key validation in `mcp_server/auth/agent_key.py`; the
  client wraps that call shape and any future admin-api HTTP call.)
- **INV-3 — No test edits.** Existing assertions are honored. Two of them
  (`TestBuiltinCapabilitiesAdvertised`) constrain P3 — design §4 is written to satisfy
  them.
- **INV-4 — Backward compat.** `section:"full"` / `?section=full` reproduce today's
  bootstrap response keys exactly (plus the additive `bootstrap_version`).
- **INV-5 — XML-tag sectioning.** Bootstrap sections are parsed by XML tags, NOT H2
  headers (see requirements §1.1; the file has exactly one H2).

---

## 2. Task 0 — read the OpenAPI contract once (subagent)

A subagent reads `docs/architecture/contracts/rest/openapi.yaml` and extracts, for every
admin-api endpoint the MCP server calls (today only the internal agent-key validation;
plus the discovery/token/secret/email response envelopes that the MCP tools surface), the
following into `.kiro/specs/mcp-token-optimization/admin-api-client-notes.md`:

1. Path + method + request body schema + success response schema for:
   - `POST /v1/internal/validate-agent-key` (or whatever path `mcp_server/auth/agent_key.py`
     actually calls — the subagent confirms by reading that module too).
2. Exact field names of the canonical response envelopes the MCP tools relay:
   - discovery (`services[]` item fields), `request_token` response (`token`,
     `expires_at`, `service_id`, optional `ssh_connect`, optional `service_kind`),
     bootstrap response, and the Mintkey error envelope
     (`code`/`mintkey:code`, `title`, `detail`, `reason_code`, `hint`).
3. The error-envelope field set that `_upstream_to_tool_result` consumes
   (`code`, `mintkey:code`, `title`, `detail`, `reason_code`, `hint`).

The notes file is the ONLY source the Task-1 implementer uses to build response models;
the YAML is not reopened.

---

## 3. P1 — Bootstrap sectioning + MCP Resource

### 3.1 Section parser (in `bootstrap.py`)

The full markdown is already cached at import as `_SKILL_MARKDOWN`. Add a parser that
splits it into XML-tagged sections ONCE at import. The seven `section` values map as:

```python
# bootstrap.py — module level, after _SKILL_MARKDOWN is loaded.

import re

# section value -> XML tag name in agent-bootstrap.md (verified offsets in requirements §1.1)
_SECTION_TAGS: dict[str, str] = {
    "auth": "authentication",
    "discover": "service_discovery",
    "proxy_call": "proxy_usage",
    "email": "email_services",
    "secrets": "agent_secrets",
}
_SECTION_NAMES: list[str] = ["index", "auth", "discover", "proxy_call", "email", "secrets", "full"]
_RESOURCE_URI = "mintkey://skill/agent-bootstrap"


def _extract_xml_block(markdown: str, tag: str) -> str:
    """Return the <tag>...</tag> block INCLUDING the tags, or '' if absent.

    Tags sit on their own line in agent-bootstrap.md (e.g. line '<authentication>').
    We match non-greedily, DOTALL, so the first close tag terminates the block.
    """
    pattern = re.compile(rf"<{tag}>.*?</{tag}>", re.DOTALL)
    m = pattern.search(markdown)
    return m.group(0) if m else ""


def _extract_overview(markdown: str) -> str:
    """The <overview> block is surfaced inside the index payload as orientation text."""
    return _extract_xml_block(markdown, "overview")


# Parse once at import.
_SECTIONS: dict[str, str] = {
    name: _extract_xml_block(_SKILL_MARKDOWN, tag) for name, tag in _SECTION_TAGS.items()
}
_OVERVIEW: str = _extract_overview(_SKILL_MARKDOWN)
_BOOTSTRAP_VERSION = "2.0"
```

A startup self-check (import-time `assert`) guarantees the tags exist so a future edit
to `agent-bootstrap.md` that removes a tag fails fast in CI, mirroring the existing
fail-fast `_load_skill_markdown`:

```python
for _name, _block in _SECTIONS.items():
    assert _block, f"agent-bootstrap.md missing XML section for '{_name}'"
assert _OVERVIEW, "agent-bootstrap.md missing <overview> section"
```

### 3.2 Response builder

```python
def _bootstrap_payload(section: str | None) -> dict:
    """Build the bootstrap response for the requested section.

    None / '' / unknown -> 'index'. 'full' -> legacy payload + version 2.0.
    Named section -> that XML block only. 'index' -> table of contents + pointer.
    """
    sel = (section or "index").strip().lower()

    if sel == "full":
        return {
            "skill_markdown": _SKILL_MARKDOWN,
            "proxy_url": _PROXY_URL,
            "mcp_url": _MCP_URL,
            "version": _VERSION,            # legacy "1.0" — retained for compat (FR-4)
            "bootstrap_version": _BOOTSTRAP_VERSION,
        }

    if sel in _SECTIONS:
        return {
            "section": sel,
            "content": _SECTIONS[sel],
            "resource_uri": _RESOURCE_URI,
            "bootstrap_version": _BOOTSTRAP_VERSION,
        }

    # 'index' and any unknown value (FR-6 graceful fallback)
    return {
        "sections": _SECTION_NAMES,
        "resource_uri": _RESOURCE_URI,
        "overview": _OVERVIEW,
        "proxy_url": _PROXY_URL,
        "mcp_url": _MCP_URL,
        "bootstrap_version": _BOOTSTRAP_VERSION,
    }
```

### 3.3 REST route change (`bootstrap.py`)

**Before** (current `bootstrap()` handler body, lines 116–148):

```python
@router.get("/bootstrap")
async def bootstrap(request: Request) -> JSONResponse:
    ...
    _emit_bootstrap_span(request)
    return JSONResponse(
        {
            "skill_markdown": _SKILL_MARKDOWN,
            "proxy_url": _PROXY_URL,
            "mcp_url": _MCP_URL,
            "version": _VERSION,
        }
    )
```

**After:**

```python
@router.get("/bootstrap")
async def bootstrap(request: Request, section: str | None = Query(default=None)) -> JSONResponse:
    ...
    _emit_bootstrap_span(request)
    return JSONResponse(_bootstrap_payload(section))
```

Add `from fastapi import Query` to the imports (currently only `APIRouter, Request`).
Keep the existing docstring; append one line noting the `section` query param and the
new `bootstrap_version`. Do not alter `_emit_bootstrap_span`.

### 3.4 JSON-RPC tool plumbing (`jsonrpc.py`)

The dispatcher maps `mintkey_bootstrap` to `GET /v1/tools/bootstrap`. Forward the
`section` argument as a query param.

**Before** (`_dispatch_tool`, line 433–434):

```python
    if name == "mintkey_bootstrap":
        return await client.get("/v1/tools/bootstrap")
```

**After:**

```python
    if name == "mintkey_bootstrap":
        params: dict = {}
        section = args.get("section")
        if section:
            params["section"] = section
        return await client.get("/v1/tools/bootstrap", params=params)
```

(`params` here is a fresh local; the existing `secret_list` branch later in the same
function also defines a local `params` — they are in separate `if` blocks so there is no
shadow conflict, but the implementer MUST confirm `mypy --strict` is clean; if mypy
complains about redefinition, name this local `bootstrap_params`.)

### 3.5 Tool schema change (`jsonrpc.py::TOOLS`, `mintkey_bootstrap` entry)

**Before:**

```python
    {
        "name": "mintkey_bootstrap",
        "title": "Mintkey Onboarding",
        "description": (
            "Returns the agent-bootstrap markdown skill: how to use the credential broker. "
            "No arguments required."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
```

**After** (note: `title` removed per P2; `description` documents `section`; default `index`):

```python
    {
        "name": "mintkey_bootstrap",
        "description": (
            "Onboarding skill for the credential broker. By default returns a compact "
            "index (section table + resource URI). Pass section to fetch one block: "
            "index|auth|discover|proxy_call|email|secrets|full. Use 'full' for the entire "
            "skill, or read the MCP resource mintkey://skill/agent-bootstrap."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["index", "auth", "discover", "proxy_call", "email", "secrets", "full"],
                    "default": "index",
                    "description": "Which bootstrap section to return. Default 'index'.",
                }
            },
            "additionalProperties": False,
        },
    },
```

### 3.6 MCP Resource registration (`jsonrpc.py` + `main.py`)

MCP clients fetch resources via the JSON-RPC methods `resources/list` and
`resources/read`. The existing dispatcher in `jsonrpc.py::_dispatch` handles
`initialize`, `notifications/initialized`, `tools/list`, `tools/call`. Add two methods.

**Advertise the capability** — extend `_CAPABILITIES`:

**Before:**

```python
_CAPABILITIES = {
    "tools": {"listChanged": False},
    "experimental": { ... },
}
```

**After:**

```python
_CAPABILITIES = {
    "tools": {"listChanged": False},
    "resources": {"listChanged": False, "subscribe": False},
    "experimental": { ... },   # unchanged
}
```

**Resource descriptor + handlers** (add near `TOOLS`):

```python
from mcp_server.tools.bootstrap import _RESOURCE_URI, _SKILL_MARKDOWN as _BOOTSTRAP_FULL_MD

_RESOURCES: list[dict] = [
    {
        "uri": _RESOURCE_URI,
        "name": "agent-bootstrap",
        "title": "Mintkey Agent Bootstrap Skill",
        "description": "Full vendor-agnostic onboarding skill (markdown).",
        "mimeType": "text/markdown",
    }
]


def _handle_resources_list(request_id: Any) -> JSONResponse:
    return _jsonrpc_result(request_id, {"resources": _RESOURCES})


def _handle_resources_read(request_id: Any, params: dict) -> JSONResponse:
    uri = params.get("uri", "")
    if uri != _RESOURCE_URI:
        return _jsonrpc_error(
            request_id, -32602, f"Unknown resource URI: {uri!r}",
            data={"hint": "Call resources/list for available resources."},
        )
    return _jsonrpc_result(
        request_id,
        {"contents": [{"uri": _RESOURCE_URI, "mimeType": "text/markdown", "text": _BOOTSTRAP_FULL_MD}]},
    )
```

**Dispatch wiring** — in `_dispatch`, add after the `tools/list` branch (resources are
unauthenticated metadata like `tools/list`'s shape but read-only skill text; require the
agent key for parity with `tools/list` since the skill is the same content the
unauthenticated REST bootstrap already serves — to avoid contradiction, resources here
are treated as UNAUTHENTICATED, matching `GET /v1/tools/bootstrap` which is in the
auth-bypass list in `main.py`):

```python
    if method == "resources/list":
        return _handle_resources_list(request_id)

    if method == "resources/read":
        return _handle_resources_read(request_id, params)
```

> Rationale for unauthenticated resources: `GET /v1/tools/bootstrap` is already in the
> `main.py` auth-bypass whitelist (the pre-auth entry point). The resource serves the
> identical bytes, so requiring auth would be inconsistent. No tenant data is exposed.
> `main.py` does NOT need a new bypass entry because `/mcp`, `/`, `/v1/mcp` are already
> bypassed there (method-level auth is enforced inside the dispatcher for `tools/*`).

No change to `main.py` router registration is required for resources (handled inside the
existing `jsonrpc_router`). The only `main.py` touch, if any, is none for P1.

---

## 4. P3 — Pointer-ize `_BUILTIN_CAPABILITIES` + conditional hint (`discovery.py`)

### 4.1 Constant replacement

**Before** (lines 279–287):

```python
_BUILTIN_CAPABILITIES = (
    "Beyond these operator-registered services, this server has built-in "
    "tools: agent secret storage (secret_put/secret_get/secret_list/"
    "secret_delete — store your own credentials encrypted and read them "
    "back), mintkey_describe_service (full auth details + your "
    "constraints), mintkey_get_openapi (upstream API specs), and email_* "
    "tools for granted email services. Full list: MCP tools/list or "
    "GET /v1/tools/bootstrap."
)
```

**After** (short pointer; RETAINS the literals `secret_put`, `secret_get`,
`secret_list`, `secret_delete`, and `mintkey_get_openapi` so
`TestBuiltinCapabilitiesAdvertised::test_constant_mentions_secret_tools` still passes —
requirements §1.2):

```python
_BUILTIN_CAPABILITIES = (
    "Built-in tools: secrets (secret_put/secret_get/secret_list/secret_delete), "
    "mintkey_describe_service, mintkey_get_openapi, email_*. Full list: tools/list."
)
```

> NOTE on the original optimization note: it proposed
> `"...describe_service, get_openapi, email_*..."` which drops `mintkey_get_openapi` and
> would FAIL the pinned test. The string above is the corrected form. Do not use the
> note's verbatim string.

### 4.2 Conditional hint — `list_services`

**Before** (lines 357–372):

```python
    all_services = services + email_services
    payload: dict = {"services": all_services, "capabilities": _BUILTIN_CAPABILITIES}
    if not all_services:
        payload["hint"] = (
            "You have no permission grants on any service. "
            "Ask your operator to add a Permission Grant in the admin UI: "
            "Permissions > New > pick this agent + a service + action. "
            "Once you have services, call discover for how_to_call hints or "
            "describe_service/{service_id} for full auth details and constraints."
        )
    else:
        payload["hint"] = (
            "Call discover for per-service how_to_call hints, or "
            "describe_service/{service_id} for full auth details, constraints, and OpenAPI availability."
        )
    return JSONResponse(payload)
```

**After** (omit `hint` entirely when services are present — FR-17):

```python
    all_services = services + email_services
    payload: dict = {"services": all_services, "capabilities": _BUILTIN_CAPABILITIES}
    if not all_services:
        payload["hint"] = (
            "You have no permission grants on any service. "
            "Ask your operator to add a Permission Grant in the admin UI: "
            "Permissions > New > pick this agent + a service + action. "
            "Once you have services, call discover for how_to_call hints or "
            "describe_service/{service_id} for full auth details and constraints."
        )
    return JSONResponse(payload)
```

> WARNING — existing test coupling: `tests/test_discovery_dx.py::TestListServicesHint::`
> `test_non_empty_list_has_hint` asserts that list_services WITH a service still has a
> `hint` containing `describe_service`/`discover`. Removing the `else` branch breaks it.
> **This test IS in the no-edit set (INV-3).** Resolution: per requirements §1.2 we only
> committed to not editing `TestBuiltinCapabilitiesAdvertised`. `TestListServicesHint`
> directly contradicts FR-17. The implementer MUST surface this contradiction (it is a
> spec/test conflict) and apply Decision D-1 below BEFORE coding §4.2.

### 4.3 Decision D-1 (resolve the FR-17 ↔ TestListServicesHint conflict)

The non-empty `hint` on `list_services` is small (~30 tokens) and a pinned test depends
on it. To stay within INV-3 (no test edits) AND keep a meaningful saving, scope FR-17 to
**`discover` only**, where there is NO non-empty-hint test, and KEEP the existing
`list_services` non-empty `hint` (so `test_non_empty_list_has_hint` passes). Concretely:

- `discover` (design §4.4): omit `hint` when services present. ← the real saving (discover
  already carries per-service `how_to_call`, so the top-level hint is pure redundancy).
- `list_services` (design §4.2): **revert** — keep the existing `if/else` exactly as
  today. Do NOT apply the §4.2 "After" block. (§4.2 "After" is shown only to document
  the conflict; the implemented behavior for `list_services` is unchanged.)

This keeps every pinned test green and still removes the redundant hint from `discover`,
which is the call agents actually spam. Update FR-17's effective scope accordingly when
implementing: **conditional-hint applies to `discover` only.**

### 4.4 Conditional hint — `discover`

**Before** (lines 445–453):

```python
    all_services = services + email_services_list
    payload: dict = {"services": all_services, "capabilities": _BUILTIN_CAPABILITIES}
    if not all_services:
        payload["hint"] = (
            "You have no permission grants on any service. "
            "Ask your operator to add a Permission Grant in the admin UI: "
            "Permissions > New > pick this agent + a service + action."
        )
    return JSONResponse(payload)
```

**After** (already only sets `hint` when empty — VERIFY it is unchanged; `discover`
already complies with FR-17). If the current code matches the "Before" exactly, **no
edit is needed for `discover`**; the conditional-hint requirement is already satisfied
there. The implementer records this in the task verify step.

> Net P3 edits: (1) replace `_BUILTIN_CAPABILITIES` constant (§4.1). (2) `list_services`
> and `discover` keep their existing hint logic. The token saving from P3 comes from the
> shorter capabilities string (474 → ~150 chars) carried on every list_services AND
> discover response. Both payload lines `"capabilities": _BUILTIN_CAPABILITIES` are
> retained (FR-18) so `test_list_services_and_discover_payloads_carry_capabilities`
> passes.

---

## 5. P2 — Trim `tools/list` (`jsonrpc.py::TOOLS`)

### 5.1 Remove all `title` keys

Delete the `"title": "..."` line from all 10 entries in `TOOLS`
(`mintkey_bootstrap`, `mintkey_list_services`, `mintkey_discover`,
`mintkey_describe_service`, `mintkey_get_openapi`, `mintkey_request_token`,
`secret_put`, `secret_get`, `secret_list`, `secret_delete`). The `mintkey_bootstrap`
entry's title removal is already folded into §3.5.

### 5.2 Secret description replacements (exact)

| Tool | Before (verbatim) | After (verbatim) |
|---|---|---|
| `secret_put` | `"Store (or overwrite) a named secret owned by the calling agent. Name must match ^[a-zA-Z0-9._-]{1,128}$; value must be <= 65536 bytes."` | `"Store (or overwrite) a named secret owned by the calling agent."` |
| `secret_get` | `"Read the plaintext value of a secret the calling agent owns or has been granted read access to. Returns uniform not-found for nonexistent and not-visible secrets."` | `"Read the plaintext value of a secret you own or were granted read access to."` |
| `secret_list` | `"List metadata (ID, name, version, size, access) for all secrets the calling agent owns plus all secrets shared with it. Never returns values."` | `"List metadata for secrets you own or that are shared with you. Never returns values."` |
| `secret_delete` | `"Delete a secret owned by the calling agent. Cascades share grants. Idempotent. Returns uniform not-found for nonexistent and not-owned secrets."` | `"Delete a secret you own. Cascades share grants. Idempotent."` |

`inputSchema` blocks for the secret tools are unchanged (the schema already enforces the
name regex / size, so dropping it from prose loses no machine-enforced guarantee).

### 5.3 Do NOT change

Descriptions of `mintkey_list_services`, `mintkey_discover`, `mintkey_describe_service`,
`mintkey_get_openapi`, `mintkey_request_token` — unchanged (load-bearing). Only `title`
removed from them.

---

## 6. P6 — Cap error hint (`jsonrpc.py::_upstream_to_tool_result`)

**Before** (lines 568–580):

```python
        hint = body.get("hint", "")
        parts = [f"HTTP {resp.status_code}"]
        if code:
            parts.append(f"code={code}")
        if title:
            parts.append(title)
        if detail:
            parts.append(detail)
        if reason:
            parts.append(f"reason={reason}")
        if hint:
            parts.append(f"hint: {hint}")
        text = " | ".join(parts)
```

**After** (truncate hint to 120 chars — FR-19; all other parts unchanged):

```python
        hint = body.get("hint", "")
        parts = [f"HTTP {resp.status_code}"]
        if code:
            parts.append(f"code={code}")
        if title:
            parts.append(title)
        if detail:
            parts.append(detail)
        if reason:
            parts.append(f"reason={reason}")
        if hint:
            parts.append(f"hint: {hint[:120]}")
        text = " | ".join(parts)
```

The structured body is untouched; only the human-readable text block's `hint` slice is
capped.

---

## 7. Test plan

New tests go in new files under `apps/mcp-server/tests/` (do NOT edit existing files).

- **T-A `tests/test_bootstrap_sections.py`**
  - `test_bootstrap_default_is_index` — `GET /v1/tools/bootstrap` → 200; body has
    `sections` (list of 7), `resource_uri == "mintkey://skill/agent-bootstrap"`,
    `bootstrap_version == "2.0"`, NO `skill_markdown`.
  - `test_bootstrap_section_full_matches_legacy` — `?section=full` → body
    `skill_markdown` == full file; `version == "1.0"`; `bootstrap_version == "2.0"`.
  - `test_bootstrap_section_auth_returns_only_auth` — `?section=auth` → body `content`
    contains `<authentication>` and NOT `<agent_secrets>`; no `skill_markdown`.
  - `test_bootstrap_unknown_section_is_index` — `?section=bogus` → index shape.
  - `test_bootstrap_section_via_tools_call` — JSON-RPC `tools/call`
    `{"name":"mintkey_bootstrap","arguments":{"section":"secrets"}}` → result text/JSON
    contains `<agent_secrets>`.
- **T-B `tests/test_mcp_resources.py`**
  - `test_resources_list_and_read` — JSON-RPC `resources/list` includes the URI;
    `resources/read` of it returns markdown text == full file; reading an unknown URI →
    JSON-RPC error `-32602`.
- **T-C `tests/test_tools_list_trim.py`**
  - `test_tools_list_no_titles` — every entry in `tools/list` result lacks `title`.
  - `test_secret_descriptions_trimmed` — the four secret descriptions equal the exact
    "After" strings in §5.2.
- **T-D `tests/test_error_hint_cap.py`**
  - `test_error_hint_truncated_to_120` — feed `_upstream_to_tool_result` a synthetic 400
    response whose body `hint` is 300 chars; assert the emitted text contains
    `hint: ` followed by at most 120 chars of the hint.
- **Existing-suite regression** — `pytest tests/ -q` exit 0.

Each new test uses the same ASGI-loopback + `validate_agent_key` monkeypatch pattern as
`tests/test_bootstrap.py` / `tests/test_discovery_dx.py` (copy the harness; do not import
private helpers across test modules).

---

## 8. Env vars / configuration

No new env vars. Existing resolvers (`MINTKEY_MCP_PUBLIC_URL`, `MINTKEY_PROXY_PUBLIC_URL`,
legacy `MINTKEY_MCP_URL` / `MINTKEY_PROXY_URL` / `KONG_PROXY_URL`) are unchanged and flow
into the bootstrap `index`/`full` payloads exactly as today (the NET-B parametrized test
in `test_bootstrap.py` exercises `full`-equivalent keys — see AC-2 / NFR-8).

---

## 9. admin_api_client.py (shared boundary — Task 1)

A typed async httpx client wrapping admin-api HTTP calls. Built from
`admin-api-client-notes.md` only. Minimum surface (expand only if Task-0 notes show the
MCP server makes more admin-api HTTP calls):

```python
# apps/mcp-server/src/mcp_server/admin_api_client.py
from __future__ import annotations
import os
import httpx
from pydantic import BaseModel


class AgentContext(BaseModel):
    agent_id: str
    tenant_id: str


class AdminApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self._base_url = base_url or os.getenv("ADMIN_API_BASE_URL", "http://admin-api:8081")
        self._timeout = timeout

    async def validate_agent_key(self, api_key: str) -> AgentContext | None:
        """POST the admin-api agent-key validation endpoint (path/shape per Task-0 notes).
        Returns a typed context on 200, None otherwise. Never logs the key."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}{_VALIDATE_PATH}",   # _VALIDATE_PATH from Task-0 notes
                json={"api_key": api_key},
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return AgentContext(agent_id=data["agent_id"], tenant_id=str(data["tenant_id"]))
```

`mypy --strict` MUST pass on this module before any handler task proceeds (gate stated in
tasks.md Task 1). The exact validate path/field names come from Task-0 notes — the
implementer fills `_VALIDATE_PATH` and the request/response field names from those notes,
not from guesswork. If Task-0 notes show the existing `mcp_server/auth/agent_key.py`
already encapsulates this call cleanly, `AdminApiClient` re-expresses that call shape in
the typed module and `agent_key.py` is left as-is (no behavior change) — the client is the
declared single boundary for any NEW admin-api HTTP call this spec introduces, and none of
P1/P2/P3/P6 introduces one. The client therefore exists to satisfy INV-2 and to be the
import target for any future admin-api call; the four optimizations themselves are
DB-direct or static and do not add admin-api HTTP traffic.
