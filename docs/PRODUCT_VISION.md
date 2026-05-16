# Mintkey product vision

## Status

Mintkey is a pre-alpha technical preview. It is suitable for local evaluation,
builder feedback, and architecture review. It is not production-ready and should
not protect production credentials yet.

## Vision

AI agents need to use real services, but they should not hold long-lived API
keys, OAuth tokens, or backend credentials. Mintkey exists to make agent access
explicit, scoped, observable, and revocable.

The long-term vision is a self-hosted credential control plane for AI agents:
operators register services and credentials once, agents discover what they are
allowed to use over MCP, and every call flows through a proxy that injects the
real credential without exposing it to the agent.

## Product promise

Agents get scoped short-lived access, never raw API keys.

## Problem

Agentic systems increasingly call third-party APIs and internal services. Today,
teams usually choose one of two poor patterns:

1. Put credentials directly in agent config, prompts, environment variables, or
   tool runtimes.
2. Let the agent fetch secrets from a secrets manager before it calls a service.

Both approaches put usable credentials into the agent's process boundary. That
is a bad fit for prompt-injected agents, long-lived automation, customer-facing
AI workflows, and regulated environments that need audit and revocation.

Teams need to answer:

- Which services can this agent use?
- Which credential backed a given request?
- What did the agent call, when, and with what result?
- Can access be revoked quickly?
- Can the backend credential rotate without reconfiguring agents?
- Can operators prove that raw credentials did not leak to logs, spans, audit
  payloads, or agent-visible responses?

## Solution

Mintkey separates agent access from backend credentials.

1. Operators register backend services and credentials.
2. Operators create agents and permission grants.
3. Agents discover allowed services over MCP.
4. Agents request scoped short-lived tokens.
5. Agents call the egress proxy with those tokens.
6. The proxy validates access, fetches the current credential, injects it
   in-flight, and forwards the request.
7. Mintkey emits audit events and observability data for the access path.

The agent never receives the raw backend credential.

## Primary users

| Cohort | Current fit | Primary value | Adoption blocker | What makes it usable |
|---|---|---|---|---|
| Builder / AI engineer | Strongest early fit | Safely connect local agents to real services | Setup complexity and sparse examples | One-command local demo, MCP client snippets, concrete integrations |
| Founder / startup CTO | Good technical-preview fit | Avoid building an internal agent credential broker | Needs packaging, release cadence, and upgrade path | Published images, clear comparison, migration docs, support path |
| Small business owner | Not direct-fit yet | Let AI tools use business apps without exposing keys | Self-hosting and security terminology are too technical | Hosted or appliance-style setup, app templates, plain-language dashboard |
| Enterprise user | Pilot fit only | Self-hosted access control, audit, SSO, tenant boundaries | Needs HA, compliance evidence, SIEM, support, security review | Helm, production guide, audit export, formal hardening, support model |

## Product principles

1. **Credential custody stays outside the agent.** Agents receive scoped access,
   not raw backend secrets.
2. **Every state change is auditable.** Configuration changes, credential
   operations, permission changes, and relevant access paths produce audit
   evidence.
3. **Contracts first.** REST, MCP, event, and vault surfaces are specified before
   implementation.
4. **Self-host first.** Operators can run the full stack locally and inspect each
   component.
5. **Pre-alpha honesty.** Public docs must be clear about what is verified, what
   is experimental, and what is not production-ready.

## Near-term product goals

### Technical preview readiness

- Make public GitHub release hygiene complete: license, security contact,
  governance docs, strict CI, dependency automation, and placeholder cleanup.
- Publish a reliable local demo that does not require an external API key.
- Provide MCP client setup guides for Claude Desktop, Claude Code, Cursor, and
  `mcp-cli`.
- Keep pre-alpha warnings visible.

### Builder usability

- Make first success possible in under 10 minutes.
- Ship examples for GitHub, Slack, Stripe, OpenAI-compatible APIs, and generic
  HTTP services.
- Show a proof walkthrough: agent discovery, token request, proxied call, audit
  event, trace, and credential non-exposure.

### Founder usability

- Explain the build-versus-adopt tradeoff.
- Publish container images and a repeatable release process.
- Document upgrade, rollback, and migration expectations.
- Define whether commercial support or a hosted preview will exist.

### Enterprise pilot readiness

- Add a production deployment guide.
- Add Helm or another Kubernetes deployment path.
- Define backup, restore, upgrade, HA, and disaster recovery procedures.
- Add SIEM/audit export direction.
- Document security testing status, including what has not been audited.

## Non-goals for the technical preview

- Replacing a general-purpose secrets manager for humans or CI/CD.
- Becoming an agent runtime or orchestration framework.
- Claiming prompt-injection prevention.
- Providing production HA or multi-region deployment out of the box.
- Claiming compliance readiness before formal security and operational work is
  complete.

## Success criteria

Mintkey becomes broadly shareable when:

- A new builder can run a local demo and connect an MCP client without reading
  the architecture folder.
- The public repository has clear license, security, governance, and
  contribution paths.
- The canonical contracts validate in CI.
- The README, docs, and marketing pages explain exactly what is ready and what is
  not.
- The product can be described in one sentence: agents get scoped short-lived
  access, never raw API keys.
