# Flows — *iteration 3 (drafted; in review)*

> The active overview is in **[`00-overview.md`](00-overview.md)**. The headline demo doc is **[`E2E-01-builder-happy-path.md`](E2E-01-builder-happy-path.md)**.

## Drafted in iteration 3 (this commit)

| ID | File |
|---|---|
| E2E‑01 | [Builder happy path](E2E-01-builder-happy-path.md) |
| F‑OP‑01 | [Operator bootstrap and first login](F-OP-01-bootstrap-and-login.md) |
| F‑OP‑02 | [Register a service](F-OP-02-register-service.md) |
| F‑OP‑03 | [Register a credential and test](F-OP-03-register-credential-and-test.md) |
| F‑OP‑04 | [Create an agent and grant permissions](F-OP-04-create-agent-and-permissions.md) |
| F‑AG‑01 | [Agent: discovery and request token](F-AG-01-discover-and-request-token.md) |
| F‑AG‑02 | [Agent: brokered call happy path](F-AG-02-brokered-call-happy-path.md) |

## Backlog (Phase 1 implementation; same template applies)
The full list of flows planned beyond iteration‑3 scope:

End‑to‑end behavioral flows as Mermaid sequence diagrams plus a checklist of which quality attribute scenarios each flow must satisfy.

## Coming in iteration 3

### Operator flows
- F‑OP‑1 Register a service.
- F‑OP‑2 Register a credential.
- F‑OP‑3 Create an agent (returns the Agent API Key once).
- F‑OP‑4 Grant a permission.
- F‑OP‑5 Rotate a credential (zero‑downtime).
- F‑OP‑6 Revoke an agent.
- F‑OP‑7 Investigate an audit trail.

### Agent flows
- F‑AG‑1 Discover services via MCP.
- F‑AG‑2 Acquire a JWT.
- F‑AG‑3 Brokered call (happy path).
- F‑AG‑4 Brokered call (denied — no permission).
- F‑AG‑5 Brokered call (token expired mid‑call).
- F‑AG‑6 Fetch OpenAPI for a service.

### System flows
- F‑SY‑1 KEK rotation.
- F‑SY‑2 Audit hash‑chain verification.
- F‑SY‑3 OTel context propagation end‑to‑end.

## Format per flow

Each flow document will contain:
1. **Goal**: one sentence.
2. **Pre‑conditions**: what must be true before the flow starts.
3. **Sequence diagram** (Mermaid).
4. **Post‑conditions**: state changes when the flow completes.
5. **Quality attribute scenarios touched**: list (e.g., `S-OPS-1`, `S-AUD-1`).
6. **Failure modes & branches**.
7. **Test outline**: what an integration test for this flow would assert.
