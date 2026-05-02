# Personas and stakeholders

## Primary personas (interact with the system directly)

### P1. Human Operator ("Operator")
- **Role**: configures the system; accountable for what agents are allowed to do.
- **Goals**:
  - Register backend services and their credentials safely.
  - Define agents and grant them service permissions.
  - Investigate "what did agent X do this morning" in under a minute.
  - Revoke an agent or rotate a credential in seconds.
- **Pain today**: secrets sprawled across `.env` files, config repos, and ticketing systems; audit requires correlating logs across N backends.

### P2. Agent Operator ("Builder")
- **Role**: builds and runs an agent that needs to call external services.
- **Goals**:
  - Get an API key for the agent and start using services without writing per‑service auth code.
  - Receive structured discovery (which services? which actions? which OpenAPI?).
  - Get usable error messages when permission is missing or a token expired.
- **Pain today**: hardcoded credentials per integration; rotation is a code change.

### P3. The Agent itself
- **Role**: machine consumer. Has an Agent API Key, talks MCP, calls the egress proxy.
- **Goals**:
  - Discover services it may use.
  - Acquire a short‑lived credential for a specific service+action.
  - Call the service via the proxy as if it were the service itself.
- **Properties**:
  - Cannot be assumed to be honest (prompt injection is a real attacker vector).
  - Cannot be assumed to be terse — may retry, parallelize, exceed token TTLs.

## Secondary personas (do not interact directly but their concerns shape the system)

### P4. Security / Compliance ("Auditor")
Concerns: confidentiality of stored credentials, immutability of audit log, rotation cadence, principle of least privilege, retention of audit data.

### P5. SRE / Platform Engineer
Concerns: observability of the system itself, deployability, upgrade story, blast radius of an outage of *us*.

### P6. Backend service owner
Concerns: their service must see traffic that looks like normal authenticated traffic from a single tenant — no special‑casing.

## Stakeholder concerns → architecture obligations

| Stakeholder       | Top concern                                               | Drives                                                   |
|-------------------|------------------------------------------------------------|----------------------------------------------------------|
| Operator          | "What did agent X do?"                                     | Per‑request audit, queryable in the admin UI.            |
| Operator          | "Rotate this credential without touching agents."          | Indirection: agents only see JWTs, never raw creds.      |
| Builder           | "Discover services, no out‑of‑band setup."                 | MCP discovery + OpenAPI serving.                         |
| Auditor           | "Encryption at rest with a real KMS."                      | Envelope encryption, KMS‑backed DEKs.                    |
| Auditor           | "Tamper‑evident audit log."                                | Append‑only log, optional hash chain.                    |
| SRE               | "Single `docker compose up` for dev."                      | Container topology + seed script.                        |
| SRE               | "Trace one request end‑to‑end."                            | OTel context propagation across MCP → broker → proxy.    |
| Backend owner     | "Don't break my auth."                                     | Proxy is transparent below the credential layer.         |

## Anti‑personas (we explicitly do not optimize for)
- Hostile agent attempting to exfiltrate credentials → architecture must contain, not enable.
- Operator trying to debug a backend by reading the agent's plaintext credential out of our logs → must be impossible by construction.
