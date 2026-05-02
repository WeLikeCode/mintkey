# Product vision

## One‑liner
> A self‑hostable broker that lets autonomous agents **discover** services, **acquire** scoped short‑lived credentials for them, and **call** them through a proxy that the real credentials never leave through — with operator‑grade observability and per‑request audit.

## Elevator pitch (engineering audience)
We sit between agents and third‑party APIs. Agents speak MCP to us to find out what they may use. We issue them a service‑bound, scope‑bound, time‑bound JWT. They call our egress proxy with that JWT. The proxy validates the JWT, looks up the real credential (API key, OAuth token, OIDC client, basic auth, …), injects it into the outbound request, and forwards it to the backend. The agent never holds a usable credential. Operators get a real‑time view of every request, latency, and error, and can revoke an agent in one click.

## Primary value propositions
1. **Containment of prompt‑injection blast radius.** A compromised agent can only use the credentials it was granted, only against the services it was granted, only for the TTL of the active JWT, and only via paths the proxy enforces.
2. **Audit at request granularity.** Every credential issuance and every proxied request is logged with agent identity, target service, latency, and outcome.
3. **Rotation without code changes.** The operator rotates the underlying credential in the vault; no agent reconfiguration is required.
4. **Discovery without out‑of‑band setup.** Agents query MCP and learn what services exist, what auth they take, and where their OpenAPI spec lives. The agent self‑bootstraps a typed client.
5. **Observability as a first‑class deliverable.** OpenTelemetry traces from MCP discovery through token issuance through proxy‑egressed call, with metrics dashboards out of the box.

## Multi‑tenancy
Mintkey is **multi‑tenant by architecture, single‑tenant by default**. A single Mintkey instance can host multiple tenants concurrently; the default `docker compose up` creates one tenant (`t_default`) and the UI hides tenant selection so a single‑tenant operator never sees the concept. Multi‑tenant deployments turn the tenant selector on and provision new tenants via the Admin REST API or AdminJS by a `PlatformAdmin` operator.

Default isolation is **row‑level** (`tenant_id` column on every domain table + Postgres Row Level Security). An opt‑in **DB‑per‑tenant** mode is available for high‑isolation deployments. See [P‑007](../proposal/P-007-multi-tenancy.md) for the full specification.

## Non‑goals (initial)
- Replacing a general‑purpose secrets manager for humans and CI.
- Being an agent runtime or orchestrator.
- Acting as an *inbound* API gateway.
- Solving prompt injection inside the agent.
- Multi‑region active‑active. MVP is single‑region.
- Sub‑millisecond proxy latency or 10k RPS per instance. We target ~100 RPS per proxy and scale horizontally.
- Multi‑tenant *agents* (an agent that spans tenants). Agents belong to exactly one tenant.

## Differentiation from references
| Capability                                              | Infisical Agent Vault | Latchkey | This product |
|----------------------------------------------------------|:----------------------:|:--------:|:------------:|
| Pulls secrets into the agent process                     | yes                    | no       | no           |
| In‑path egress proxy injecting credentials               | no                     | yes      | yes          |
| MCP‑native service discovery                             | no                     | partial  | yes          |
| OpenAPI spec served per service                          | no                     | no       | yes          |
| OTel traces spanning MCP → token → proxy → backend       | partial                | no       | yes          |
| Self‑host via single `docker compose up`                 | yes                    | n/a      | yes          |
| Pluggable backend auth schemes (API key/OAuth/OIDC/basic)| partial                | yes      | yes          |
| Per‑agent permission model with one‑click revoke         | partial                | yes      | yes          |

*(Comparisons are best‑effort against publicly available material at the time of writing; corrections welcome.)*

## Success criteria for the architecture phase
- A second engineer can read `docs/` end‑to‑end in under 60 minutes and explain back what we are building, what's hard, and where the open decisions are.
- Every "we will build X" claim is anchored to (a) a quality attribute scenario it satisfies, (b) at least one identified risk, and (c) either an Accepted ADR or an open proposal.
- Implementability check: every container in the C4 container view has at least one viable open‑source candidate technology (recorded in iteration 2).
