# Glossary

Use these terms consistently across all docs and contracts. If a term needs to change, change it here first.

| Term                          | Definition |
|-------------------------------|------------|
| **Agent**                     | An autonomous process (typically AI/LLM‑driven) that consumes our system to call backend services. Identified by an Agent API Key. |
| **Agent API Key**             | The long‑lived credential the Agent presents to us. Hashed at rest. Used to authenticate the agent when it calls MCP or the credential broker. |
| **Operator**                  | Human user with access to the Admin Console. Can register services, manage credentials, manage agents, view audit. |
| **Service**                   | A backend system the Agent may call (typically a REST API). Defined by name, base URL, auth scheme, and zero‑or‑more OpenAPI documents. |
| **Action** (a.k.a. **Scope**) | A named subset of operations on a Service that an Agent may be granted (e.g., `read:contacts`, `send:email`). May map to OpenAPI tags/operations. |
| **Credential**                | The real secret used to authenticate to a Service: API key, OAuth client + tokens, OIDC client, basic auth pair, mTLS cert, etc. Stored encrypted. **Never leaves the data plane.** |
| **Vault** (lowercase)         | The component that stores Credentials encrypted at rest. Pluggable backend per [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md): encrypted file on disk (v1, default), HashiCorp Vault (v2), or SQL+KMS (v3). |
| **JWT** (a.k.a. **Brokered Token**) | The short‑lived, signed, scope‑bound token the Agent receives from the Credential Broker and presents to the Egress Proxy. The agent never sees the underlying Credential. |
| **Credential Broker**         | The control‑plane component that mints JWTs after authenticating the Agent and checking permissions. |
| **Egress Proxy**              | The data‑plane component the Agent calls instead of the backend Service. Validates the JWT, looks up the Credential, injects it, forwards the request, scrubs any echoed credential from the response. |
| **MCP Server**                | The Model Context Protocol surface we expose to Agents for discovery and token request. |
| **Admin Console**             | The minimalistic web UI used by Operators. |
| **Admin REST API**            | The backend serving the Admin Console (and usable directly). |
| **BFF** (Backend‑for‑Frontend)| Where the Admin REST API exposes UI‑specific shapes (paginated list views, etc.). |
| **Audit Event**               | A record of one auditable action: token issuance, token use, permission change, credential rotation, etc. Append‑only. |
| **Permission Grant**          | A tuple `(agent, service, action, optional constraints)` allowing the agent to request a JWT with that scope. |
| **DEK / KEK**                 | Data Encryption Key / Key Encryption Key (envelope encryption). DEK encrypts the credential; KEK encrypts the DEK; KEK lives in a KMS. |
| **Control plane**             | Components that manage configuration and issue tokens. Read‑write but not on the per‑request hot path. |
| **Data plane**                | The Egress Proxy. On the per‑request hot path; latency‑sensitive. |
| **Discovery**                 | The MCP‑exposed read surface returning the services and actions visible to the calling agent. |
| **JWKS**                      | JSON Web Key Set — the published public keys of the broker, fetched by the proxy to verify JWT signatures. |
| **Tenant**                    | A logically isolated organization within a Mintkey instance. Owns its own services, credentials, agents, permissions, audit, and operators (via memberships). Default deployment has one `t_default` tenant; multi‑tenant deployments host many. See [P‑007](../proposal/P-007-multi-tenancy.md). |
| **OperatorTenantMembership**  | The link between an Operator and a Tenant, with a role. One Operator can belong to multiple Tenants with different roles per Tenant. |
| **PlatformAdmin**             | A meta‑role above Tenants. Can create/delete Tenants, query cross‑tenant audit, manage instance‑level settings. Implemented as a boolean on `Operator`, not as a special Tenant. |
| **Tenancy model**             | Multi‑tenant by architecture, single‑tenant by default. Default isolation: row‑level (`tenant_id` column + Postgres RLS). Opt‑in: DB‑per‑tenant for high‑isolation tier. See [P‑007](../proposal/P-007-multi-tenancy.md). |
| **System actor (`system_…`)** | Non‑human, non‑agent identity used for system‑initiated audit events (KEK rotation jobs, audit‑chain verification job, change‑channel heartbeat publisher). ULID prefix `system_…`. See [ADR‑0017.13](../01-architecture/adr/0017-round-3-corrections.md). |
