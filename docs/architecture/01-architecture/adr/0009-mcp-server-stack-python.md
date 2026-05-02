# ADR‑0009: MCP Server stack — Python + Anthropic Python SDK

## Status
Accepted — 2026-05-10. Promoted from [`docs/proposal/P-008-mcp-server-stack.md`](../../proposal/P-008-mcp-server-stack.md), Option A (the proposal's recommendation).

## Context
[P‑008](../../proposal/P-008-mcp-server-stack.md) compared three options for the MCP Server (C4): Python + Anthropic Python SDK, TypeScript + Anthropic TS SDK, Go + community SDK. The decisive forces:
- **Cohesion with the Admin REST API** (Python + FastAPI per [ADR‑0005](0005-admin-tech-stack.md)) — same Pydantic models, same DB drivers, same OIDC client, same observability story.
- **Phase 3 readiness** — the [roadmap](../../00-vision/06-roadmap.md) Phase 3 turns the MCP Server into both server and client (MCP‑to‑MCP proxy). The Anthropic Python SDK has both primitives.
- **Performance is not a deciding factor** — the MCP Server is not on the proxy hot path.

## Decision

### Language and SDK
- **Language**: **Python 3.12+**.
- **MCP SDK**: **`mcp` (Anthropic Python SDK)** — the official server and client implementation maintained by Anthropic.
- **Transport (default)**: HTTP/SSE for compose‑deployable agents. stdio is supported for CLI agent demos.

### Library pins (versions finalized in iteration 2 closeout)
| Concern              | Choice                                                       |
|----------------------|--------------------------------------------------------------|
| Language             | Python 3.12+                                                 |
| MCP SDK              | `mcp` (Anthropic Python SDK)                                 |
| Web/transport        | FastAPI (when MCP transport is HTTP/SSE)                     |
| Validation           | Pydantic v2                                                  |
| DB driver            | `asyncpg`                                                    |
| Type‑safe queries    | `sqlc`‑style codegen or SQLAlchemy 2.x (decision in iteration‑2 closeout ADR) |
| OTel                 | `opentelemetry-instrumentation-fastapi` + manual spans on tool calls |
| Testing              | `pytest` + `pytest-asyncio` + `httpx` + `testcontainers`      |
| Auth (agent)         | Bearer Agent API Key in HTTP header for HTTP/SSE; env‑injected for stdio |

### Code organization
- The MCP Server is a separate container (`mintkey/mcp`) but **shares the Python codebase organization conventions** of the Admin REST API.
- A **shared Python package `mintkey-models`** holds Pydantic models for `Service`, `Agent`, `PermissionGrant`, `Tenant`, `Operator`, etc., used by both the Admin REST API and the MCP Server. Single source of truth for domain models.

### Multi‑tenancy
The MCP Server enforces tenant scoping by:
- Resolving the agent's tenant from the Agent API Key on every connection / request.
- Setting `SET LOCAL app.current_tenant = <agent.tenant_id>` at the start of each DB transaction (per [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md)).
- Filtering all `list_services`, `describe_service`, etc. results by the agent's tenant — at the application layer *and* by virtue of RLS.

## Consequences

### Positive
- **Stack cohesion** — the control‑plane Python footprint is one language, one DB driver, one OIDC client, one OTel SDK shared across Admin API and MCP Server.
- **Shared domain models** via `mintkey-models` eliminate the "two implementations of the same Pydantic model" maintenance tax that a TypeScript MCP Server would have.
- **Phase 3 MCP‑to‑MCP proxy** is a clean extension: the Anthropic Python SDK has client primitives, so we add an upstream MCP client to the same process without re‑platforming.

### Costs
- The Anthropic Python SDK lags the TypeScript SDK at major MCP spec releases by some weeks. We accept the lag because the agent surface we expose is small and stable.
- Python's async concurrency requires care for long‑lived MCP sessions. Mitigated by the `mcp` SDK's session abstractions.

### Risks
- **SDK pace**: if the MCP spec evolves faster than the Python SDK can keep up, we may have to upstream patches or temporarily fork. Mitigation: pin the SDK version per release; track Anthropic's roadmap.
- **Connection management** for HTTP/SSE under load: monitored via OTel; iteration 3 flow ADRs document the session lifecycle.

## Implications
- [`02-container-view.md`](../02-container-view.md) — C4 (MCP Server) is realized by a Python process; iteration 2 closeout updates the view.
- [`05-deployment/README.md`](../../05-deployment/README.md) — `mintkey/mcp` is a separate container running Python.
- [`docs/contracts/mcp/`](../../contracts/mcp/) — iteration 4 schemas are emitted by the MCP Server's typed Python handlers (Pydantic + the SDK's tool decorators) round‑trippable to a checked‑in JSON Schema set.
- [`07-kiro-readiness.md`](../../00-vision/07-kiro-readiness.md) — the "add an MCP tool" pattern targets Python + the `mcp` SDK.
- The shared `mintkey-models` Python package is added to the iteration‑2 deliverables.

## Honest alternative kept on file
If the SDK pace ever blocks us, the MCP Server can be re‑platformed to **TypeScript + `@modelcontextprotocol/sdk`**. The agent‑facing contract (the MCP tool surface) is the same in either language, so this is a swap of one container without breaking the agents.

## Open follow‑ups (iteration 2 closeout)
- Pin the specific `mcp` SDK version (and Anthropic's release cadence policy).
- DB access pattern: `sqlc`‑style codegen vs. SQLAlchemy 2.x — decided in the Python‑stack pin ADR.
- Decision on whether the MCP Server runs on HTTP/SSE only or supports stdio in compose. *Lean: HTTP/SSE primary; stdio for CLI demos.*

## Related
- [P‑008 mcp‑server‑stack](../../proposal/P-008-mcp-server-stack.md) — Accepted (this ADR).
- [ADR‑0005 admin tech stack](0005-admin-tech-stack.md) — Python is already in the control plane.
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — every MCP tool invocation scopes to the agent's tenant.
- [Roadmap Phase 3](../../00-vision/06-roadmap.md) — MCP‑to‑MCP proxy is built on the same SDK.
