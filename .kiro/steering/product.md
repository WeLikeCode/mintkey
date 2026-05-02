# Product

**Codename:** mintkey
**Phase:** MVP
**Architect:** Alexandru Iacobescu <alexandru.iacobescu@mintkey.dev>

## What it is

Mintkey is a self-hostable agentic credential broker. It sits between autonomous AI agents and the third-party services they need to call. Agents discover services via MCP, receive a scoped short-lived JWT, and call backends through an egress proxy that injects the real credential — which the agent never sees.

## Why it exists

AI agents increasingly need to call third-party services but today's patterns — baked-in credentials or hand-rolled vault pulls — leave the live credential in the agent's process memory, provide no per-request audit, and make rotation a code change. Mintkey solves this by brokering access: agents discover services via MCP, receive a scoped short-lived JWT, and call backends through an egress proxy that injects the real credential. The agent never holds a usable credential. Operators get a real-time view of every request, latency, and error, and can revoke an agent in one click.

## Primary value propositions

1. **Containment** — a compromised agent can only use the credentials it was granted, only against the services it was granted, only for the TTL of the active JWT.
2. **Audit at request granularity** — every credential issuance and every proxied request is logged with agent identity, target service, latency, and outcome.
3. **Rotation without code changes** — the operator rotates the underlying credential; no agent reconfiguration required.
4. **MCP-native discovery** — agents query MCP and learn what services exist, what auth they take, and where their OpenAPI spec lives.
5. **Observability as a first-class deliverable** — OTel traces from MCP discovery through token issuance through proxy-egressed call, with metrics dashboards out of the box.

## Tenancy

Multi-tenant by architecture, single-tenant by default. Default isolation: row-level (`tenant_id` column + Postgres RLS). Opt-in: DB-per-tenant for high-isolation deployments. (ADR-0008)

## Deployment target

Self-hostable on-prem / private cloud via `docker compose up`. Single-region MVP. No multi-region active-active in scope.

## Regulated industry

Light (privacy only). Audit retention, encryption-at-rest, and tamper-evident logs are required. No sector-specific regulation (HIPAA/PCI/HIPAA) in scope for MVP.

## Non-goals (MVP)

- Replacing a general-purpose secrets manager for humans and CI.
- Being an agent runtime or orchestrator.
- Acting as an inbound API gateway.
- Solving prompt injection inside the agent.
- Multi-region active-active.
- Sub-millisecond proxy latency or 10k RPS per instance.
