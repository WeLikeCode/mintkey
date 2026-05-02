# P‑008 — MCP Server tech stack

**Status**: Accepted (→ [ADR‑0009](../01-architecture/adr/0009-mcp-server-stack-python.md)) — 2026-05-10. Selected the recommended **Option A** (Python + Anthropic Python SDK).

> **Outcome**: Accepted as recommended. MCP Server is Python 3.12+ using the official Anthropic `mcp` SDK. Cohesion with the Admin REST API drives the choice — shared Pydantic models in a `mintkey-models` package, shared DB drivers, shared OTel SDK. HTTP/SSE is the default transport; stdio supported for CLI agent demos. Phase‑3 MCP‑to‑MCP proxy uses the same SDK's client primitives. TypeScript is preserved as the documented re‑platform path if SDK pace ever becomes a blocker. See [ADR‑0009](../01-architecture/adr/0009-mcp-server-stack-python.md).

## Question
What language and library implements the **MCP Server** (C4 in [container view](../01-architecture/02-container-view.md))?

## Context
The MCP Server speaks the Model Context Protocol to agents. Its responsibilities (from [container view](../01-architecture/02-container-view.md)):
- Authenticate the agent via Agent API Key.
- Expose discovery tools (`list_services`, `describe_service`, `get_openapi`).
- Expose `request_token(service_id, action, ttl_seconds?)` that delegates to the Credential Broker.
- Be stable across agents (its tool surface is the agent‑facing contract).
- Be tenant‑aware: every tool call is scoped to the agent's tenant ([ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md)).

### Forces
- **MCP SDK maturity**: Anthropic's reference SDK is most mature in **TypeScript**, then **Python**, then community Go.
- **Stack cohesion**: the Admin REST API is **Python** ([ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md)); the Credential Broker and Vault Adapter are likely **Go** (security‑critical components).
- **Performance**: the MCP server is *not* on the proxy hot path; latency budgets are looser.
- **Observability**: every reasonable language has good OTel SDKs.
- **TDD ergonomics**: pytest, vitest, and Go testing are all viable.
- **Phase‑3 MCP‑to‑MCP proxy** ([roadmap](../00-vision/06-roadmap.md)): in Phase 3 the MCP Server gets an *upstream MCP client* role too. The chosen language must support both server and client roles in the same SDK.

## Options

### Option A — Python + Anthropic Python SDK (`mcp` package)
- Implements MCP server using Anthropic's official Python SDK. Same Python interpreter as the Admin REST API.
- **Pros**:
  - **Stack cohesion** with the Admin REST API: shared Pydantic models for service/agent/permission, shared OIDC and DB drivers, shared logging.
  - The Python SDK has both server and client primitives, making the Phase‑3 MCP‑to‑MCP proxy a natural extension.
  - Type‑safety via Pydantic; tooling parity with the Admin REST API.
  - `pytest` ecosystem is excellent for TDD.
- **Cons**:
  - Slightly less mature than the TypeScript SDK; lags the spec by weeks at major releases.
  - Python concurrency is async‑heavy; long‑lived MCP sessions need careful asyncio handling.

### Option B — TypeScript + `@modelcontextprotocol/sdk` (Node.js)
- Implements MCP server using Anthropic's reference TypeScript SDK. Adds another Node container alongside AdminJS.
- **Pros**:
  - **Most mature SDK** — Anthropic's reference, gets new MCP spec features first.
  - Strong type system; good DX with VS Code.
  - Both server and client primitives in the same package.
- **Cons**:
  - Adds a third language for a single container (Python + Node + Go already; this would be Python + Node × 2 + Go).
  - No code reuse with the Admin REST API; we'd reimplement Pydantic models as TypeScript types.
  - More tooling: tsc, eslint, vitest, pnpm — different from the Admin REST API's stack.

### Option C — Go + community SDK (e.g., `mark3labs/mcp-go` or `modelcontextprotocol/go-sdk`)
- Implements MCP server in Go.
- **Pros**:
  - **Stack cohesion** with the Broker, Vault Adapter, Kong‑syncer, Egress Proxy plugin (all Go).
  - Best performance and lowest memory footprint.
  - Strongest concurrency model for long‑lived sessions.
- **Cons**:
  - Community SDKs are less mature than Anthropic's official Python and TypeScript SDKs; may lag the spec.
  - Risk of having to maintain or fork the SDK.
  - No code reuse with the Admin REST API.

## Comparison matrix

| Dimension                                       | A. Python | **B. TypeScript** | C. Go |
|--------------------------------------------------|:---------:|:-----------------:|:-----:|
| Anthropic SDK maturity                           | ✓        | ✓✓ canonical      | ⚠ community |
| Stack cohesion with Admin REST API (Python)      | ✓✓        | ✗                 | ✗     |
| Stack cohesion with Broker / Vault (Go)          | ✗         | ✗                 | ✓✓    |
| Phase‑3 MCP‑to‑MCP client maturity              | ✓         | ✓✓               | ⚠     |
| New language(s) added to control plane           | none     | +1 (Node × 2)    | none (Go is already there) |
| Performance / memory                             | ⚠ async   | ⚠ async          | ✓✓    |
| TDD ergonomics                                   | ✓✓ pytest | ✓ vitest         | ✓ go test |
| Pydantic / Zod / struct‑tag validation           | ✓✓        | ✓                 | ✓     |
| Operator skill required to debug                 | Python    | Node + TS        | Go    |

## Recommendation

**Option A — Python + Anthropic Python SDK** for v1.

Reasoning:
1. **Cohesion with the Admin REST API** dominates the analysis. The MCP Server reads the same `service`, `agent`, `permission`, and `tenant` records as the Admin API. Sharing Pydantic models and DB queries (`sqlc`‑style or via SQLAlchemy) is significant code reuse. Implementing the same models twice in TypeScript is the kind of wasteful work we're already trying to minimize ([ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md) chose AdminJS to avoid hand‑rolling a UI).
2. **The Python SDK is mature enough** for production server use today. New MCP spec features may arrive in TypeScript first, but our needs (a small server with a stable tool surface) don't push the spec edge.
3. **The MCP Server is not on the latency hot path** — the proxy is. The performance argument for Go doesn't apply.
4. **Phase 3 readiness**: the Python SDK has both server and client primitives, so MCP‑to‑MCP proxy in Phase 3 is a clean extension rather than a re‑platform.

### Honest alternative
If a future audit concludes "the MCP Server's surface drifts faster than Anthropic's Python SDK can keep up", we re‑platform to **TypeScript (Option B)**. The contract is the agent‑facing MCP surface, which is the same in either language.

## Tech stack pinning (if accepted)

| Concern                | Choice                                                     |
|------------------------|------------------------------------------------------------|
| Language               | Python 3.12+                                               |
| Web framework          | FastAPI (HTTP transport) or stdio runner depending on transport mode |
| MCP SDK                | `mcp` (Anthropic Python SDK)                               |
| Validation             | Pydantic v2 (shared with Admin REST API)                   |
| DB access              | `asyncpg` + (`sqlc`‑style or SQLAlchemy 2.x)               |
| OTel                   | `opentelemetry-instrumentation-fastapi` + manual spans for tool calls |
| Testing                | `pytest` + `pytest-asyncio` + `httpx` + `testcontainers`    |

## Implications
- The MCP Server is a separate container (`mintkey/mcp`), but shares the same Python codebase organization conventions as the Admin REST API.
- A shared Python package (`mintkey-models`) holds Pydantic models for `Service`, `Agent`, `PermissionGrant`, `Tenant`, etc., used by both Admin API and MCP Server.
- The MCP Server enforces tenant scoping by setting `SET LOCAL app.current_tenant = <agent.tenant_id>` at the start of each MCP tool invocation.
- Phase‑3 MCP‑to‑MCP proxy adds a *client* role to the same MCP Server, reusing the SDK's client primitives.

## Open follow‑ups
- Pin specific `mcp` SDK version once iteration 2 completes.
- Decide MCP transport for v1: HTTP (server‑sent events) vs. stdio. *Lean: HTTP/SSE for compose‑deployable; stdio for CLI agent demos.*
- Whether to ship a shared `mintkey-models` Python package or duplicate models per service. *Lean: shared package.*
- How the agent authenticates: Bearer Agent API Key in the HTTP header for HTTP transport; environment‑injected for stdio. Captured in iteration 4 contracts.

## Related
- [ADR‑0005 admin tech stack](../01-architecture/adr/0005-admin-tech-stack.md) — Python is already in the control plane.
- [ADR‑0008 multi‑tenancy](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md) — every MCP tool invocation scopes to the agent's tenant.
- [Roadmap](../00-vision/06-roadmap.md) Phase 3 — MCP‑to‑MCP proxy.
