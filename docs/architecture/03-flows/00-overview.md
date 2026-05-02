# Iteration 3 — End‑to‑end flows

This iteration captures the major user journeys as **Mermaid sequence diagrams + structured pre/post‑conditions + quality‑attribute checklists + test plans**. Each flow is the input from which Kiro generates a spec triple (requirements + design + tasks) for the implementing components.

## Iteration‑3 deliverables (this commit)

| ID | Flow | Audience |
|---|---|---|
| **[E2E‑01](E2E-01-builder-happy-path.md)** | **Builder happy path — operator bootstrap → service registration → credential + test → create agent → MCP discovery → brokered call → observability check** | end‑to‑end demo |
| [F‑OP‑01](F-OP-01-bootstrap-and-login.md) | Operator bootstrap and first login | operator |
| [F‑OP‑02](F-OP-02-register-service.md) | Register a service (with optional OpenAPI link) | operator |
| [F‑OP‑03](F-OP-03-register-credential-and-test.md) | Register a credential and test it | operator |
| [F‑OP‑04](F-OP-04-create-agent-and-permissions.md) | Create an agent and grant permissions | operator |
| [F‑AG‑01](F-AG-01-discover-and-request-token.md) | Agent: MCP discovery and request a token | agent |
| [F‑AG‑02](F-AG-02-brokered-call-happy-path.md) | Agent: brokered call (happy path) | agent |

## Out of iteration‑3 scope (Phase 1 implementation; same template applies)
- F‑OP‑05 Rotate a credential (zero downtime).
- F‑OP‑06 Revoke an agent.
- F‑OP‑07 Investigate the audit log.
- F‑AG‑03 Brokered call (denied — no permission).
- F‑AG‑04 Brokered call (token expired mid‑call).
- F‑AG‑05 Fetch OpenAPI for a service.
- F‑SY‑01 KEK rotation.
- F‑SY‑02 Audit hash‑chain verification job.
- F‑SY‑03 OTel context propagation end‑to‑end.

These follow the same template; they're written as Phase 1 implementation reaches them.

## Format per flow

Every flow doc has:
1. **Goal** — one sentence.
2. **Actors** — who participates.
3. **Pre‑conditions** — state required before the flow starts.
4. **Sequence diagram** (Mermaid).
5. **Post‑conditions** — state changes when complete.
6. **Quality attribute scenarios touched** — list of `S‑*‑*` from [`03-quality-attributes.md`](../01-architecture/03-quality-attributes.md).
7. **Failure modes and branches** — what can go wrong.
8. **Test plan** — unit + integration + live‑smoke layers.
9. **Kiro spec inputs** — what to feed Kiro to generate requirements + design + tasks.

## Test posture (SDD + TDD)

Per the operator's directive, every flow has three test layers:

| Layer | Scope | Speed | When run |
|------|-------|-------|----------|
| **Unit** | One function or handler. Mock all dependencies. | < 10 ms each | Pre‑commit; every CI step |
| **Integration** | Real Postgres + Kong + Keycloak via testcontainers; one component at a time end‑to‑end against real deps. | 1–30 s each | CI on every PR |
| **Live smoke / e2e** | Full `docker compose up` stack; one user journey end‑to‑end. | 30–90 s | Merge gate; Phase 1 acceptance |

Kiro consumes the **test plan section** of each flow to generate failing tests first (TDD), then the implementation that satisfies them.

## Contract impact identified during iteration 3

Iteration 3 surfaces a small set of additions for the iteration‑4 contracts (tracked for the contract review pass):

| Addition | Source flow | Where it lands |
|----------|-------------|----------------|
| `POST /v1/tenants/{tid}/services/{sid}/test` endpoint | [F‑OP‑03](F-OP-03-register-credential-and-test.md) | OpenAPI |
| `service.test_executed` audit event | [F‑OP‑03](F-OP-03-register-credential-and-test.md) | audit‑event schema |
| `tenant.bootstrap_completed` audit event | [F‑OP‑01](F-OP-01-bootstrap-and-login.md) | audit‑event schema |
| `service.openapi_url` and optional `service.openapi_etag` | [F‑OP‑02](F-OP-02-register-service.md) | Service schema |
| `agent.mcp_endpoint` (computed, not persisted) | [F‑OP‑04](F-OP-04-create-agent-and-permissions.md) | Agent response schema |

## Reading order for an implementer
1. **[E2E‑01](E2E-01-builder-happy-path.md)** — see the whole story end to end.
2. The component flows referenced from E2E‑01, in execution order.
3. The corresponding sections of [`02-tech-stack/`](../02-tech-stack/) and the relevant ADRs to understand the mechanism.
4. The contracts under [`docs/contracts/`](../contracts/) to see the wire surface.
5. Generate Kiro spec triples from each flow's "Kiro spec inputs" section.
