# Problem statement

## Context
Autonomous and semi‑autonomous AI agents increasingly need to call third‑party services — sending email, querying CRMs, hitting internal microservices, browsing SaaS APIs — to perform real work. To do that, they need credentials.

Today, two unsatisfying patterns dominate:

1. **Bake the credential into the agent.** Embedded API keys in environment variables, prompts, configuration files, or "tool definitions". Easy to leak, painful to rotate, impossible to audit at request granularity, and gives the agent the maximum blast radius forever.
2. **Hand‑roll a per‑integration secret retrieval.** Pull the credential from HashiCorp Vault, Infisical, AWS Secrets Manager, etc. before each call. Better than (1) for rotation, but the live credential still lands in the agent's process memory and prompt context — which interacts poorly with prompt injection.

Neither pattern gives an honest answer to the questions that matter for production use:

- *Which services can this agent use?* (discovery)
- *What did this agent actually do with this credential?* (audit at request granularity)
- *How do I rotate the underlying credential without touching the agent?* (decoupling)
- *How do I revoke an agent's access in seconds, not on next deploy?* (immediacy)
- *How do I prevent the agent from being tricked into exfiltrating the credential itself?* (prompt‑injection containment)

## Reference points
- **Infisical Agent Vault** (`https://github.com/Infisical/agent-vault`) — pulls secrets to the agent's environment. Solves rotation but the live credential still lands in the agent.
- **Latchkey** (`https://imbue.com/blog/latchkey`) — argues for a brokered, proxy‑based model where the agent receives a short‑lived token and the real credential is injected by an in‑path proxy. We adopt and extend this thesis.

## The problem we are solving
> AI agents need a way to **discover** which external services they may use, **acquire** scoped, short‑lived credentials for them, and **call** them through a path that never exposes the underlying secret to the agent — with full operator visibility and per‑request audit.

## Non‑problems (out of scope, at least initially)
- Replacing a general‑purpose secrets manager for human developers and CI/CD pipelines. (HashiCorp Vault, Infisical, etc., remain better at that.)
- Providing the agents themselves. We broker access; we are not an agent runtime.
- Acting as a generic API gateway for non‑agent traffic. The proxy is on the agent's egress path, not in front of inbound API consumers.
- Solving prompt injection inside the agent. We *contain* its impact on credentials; we do not prevent it.

## What success looks like
A self‑hoster runs `docker compose up`, opens an admin console, registers a service and a credential, creates an agent, grants it a permission, and the agent immediately discovers the service over MCP, requests a JWT, and calls the backend through our proxy — and the operator sees every step in Jaeger, with one trace from MCP discovery through token issuance through proxied backend call.

Anything less is just a fancier secrets file.
