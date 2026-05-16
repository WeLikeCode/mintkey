# Agent credential risk: direct API keys vs Mintkey

This document provides diagram source for explaining why raw long-lived API keys
are a poor fit for AI agents, and how Mintkey changes the blast radius. Mintkey
does not prevent prompt injection. It limits what a compromised agent can expose:
the agent receives a short-lived, scoped brokered token instead of the underlying
long-term credential.

## Without Mintkey: direct long-lived API key

```mermaid
sequenceDiagram
  autonumber
  participant Operator
  participant Agent
  participant API as External API
  participant Attacker

  Operator->>Agent: Configure long-lived API key
  Agent->>API: Call API with raw key
  API-->>Agent: Return data
  Attacker->>Agent: Prompt injection asks for secrets
  Agent-->>Attacker: Leaks raw API key
  Attacker->>API: Reuse leaked key until revoked
  API-->>Attacker: Authorized access with long-lived credential
```

The key problem is not only that a key can leak. The problem is that leaked API
keys are commonly long-lived, broad in scope, and valid outside the agent runtime.
Once copied into an attacker-controlled place, the credential keeps working until
the operator detects the leak and rotates or revokes it.

## Without Mintkey: prompt-injection blast radius

```mermaid
flowchart LR
  prompt["Prompt injection"] --> agent["Agent process"]
  env["Environment variable or config"] --> agent
  memory["Tool memory and logs"] --> agent
  agent --> leak["Raw API key exposed"]
  leak --> attacker["Attacker-controlled endpoint"]
  attacker --> replay["Replay against external API"]
  replay --> impact["Long-lived access, high blast radius"]

  classDef danger fill:#fff1f0,stroke:#c73a31,color:#5f1712,stroke-width:2px;
  classDef neutral fill:#f7faf8,stroke:#cfd8d4,color:#101820;
  class prompt,leak,attacker,replay,impact danger;
  class agent,env,memory neutral;
```

## With Mintkey: brokered short-lived access

```mermaid
sequenceDiagram
  autonumber
  participant Agent
  participant MCP as Mintkey MCP Server
  participant Broker as Credential Broker
  participant Proxy as Egress Proxy
  participant Vault as Secure Credential Store
  participant API as External API
  participant Attacker

  Agent->>MCP: Discover allowed services
  Agent->>Broker: Request scoped token for one service
  Broker-->>Agent: Return short-lived brokered JWT
  Agent->>Proxy: Call service with brokered JWT
  Proxy->>Broker: Validate token, scope, tenant, agent
  Proxy->>Vault: Fetch underlying credential for request
  Vault-->>Proxy: Return credential inside trusted path
  Proxy->>API: Inject real API key on the wire
  API-->>Proxy: Return response
  Proxy-->>Agent: Return response without raw credential
  Attacker->>Agent: Prompt injection asks for secrets
  Agent-->>Attacker: Leaks short-lived scoped JWT only
```

The underlying credential remains in Mintkey's trusted path. The agent can still
be compromised, but what it can leak is a temporary, service-bound token. That
token expires and is validated by Mintkey-controlled infrastructure before it can
be used. This is a containment model, not a promise that prompt injection cannot
happen.

## With Mintkey: reduced blast radius

```mermaid
flowchart LR
  operator["Operator stores real API key"] --> store["Encrypted credential store"]
  agent["Agent"] --> token["Short-lived scoped JWT"]
  token --> proxy["Egress proxy validates token"]
  store --> proxy
  proxy --> inject["Inject credential per request"]
  inject --> api["External API"]
  injection["Prompt injection"] --> agent
  agent --> leaked["Temporary token leaked"]
  leaked --> expires["Expires quickly and is scope-bound"]
  expires --> reduced["Reduced credential blast radius"]

  classDef safe fill:#eafff6,stroke:#20c389,color:#0b3a2c,stroke-width:2px;
  classDef trusted fill:#f7faf8,stroke:#101820,color:#101820,stroke-width:1.5px;
  classDef warning fill:#fff8e1,stroke:#c7a64a,color:#4a3a0a,stroke-width:2px;
  class operator,store,proxy,inject,api safe;
  class agent,token trusted;
  class injection,leaked,expires,reduced warning;
```

## Core message

| Pattern | What the agent holds | If prompt-injected | Operator outcome |
|---|---|---|---|
| Direct API key | Raw long-term credential | Credential can be copied and replayed directly against the API | Detect, rotate, revoke, and investigate broad exposure |
| Mintkey brokered access | Short-lived scoped JWT | Temporary token may leak, but the real API key stays hidden | Expiry, scope, proxy validation, audit trail, and credential rotation without agent changes |

