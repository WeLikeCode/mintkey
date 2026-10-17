# Agent Secret Storage

## ADDED Requirements

### Requirement: Agent can store a named secret
An agent authenticated with its `mk_agent_` API key SHALL be able to store a named secret value via the `secret_put` MCP tool. The secret is scoped to (tenant, owning agent, name); names MUST be unique per agent. The value MUST be envelope-encrypted (fresh AES-256-GCM DEK per write, DEK wrapped by the vault KEK) before it reaches storage. The value MUST be at most 65536 bytes. Storing to an existing name overwrites and increments the version. `tenant_id` and the owner identity MUST come from the authenticated agent context, never from tool input.

#### Scenario: First store of a secret
- **WHEN** an active agent calls `secret_put` with name `db-password` and a value within the size limit
- **THEN** the system stores the encrypted value, returns the secret's wire ID (`sec_` prefix), name, and version 1, and emits an `agent_secret.created` audit event whose payload contains identifiers only — no secret material

#### Scenario: Overwrite an existing secret
- **WHEN** the owning agent calls `secret_put` with a name it already used
- **THEN** the stored value is replaced with new envelope encryption, the version increments, and an `agent_secret.updated` audit event is emitted

#### Scenario: Oversized value rejected
- **WHEN** an agent calls `secret_put` with a value larger than 65536 bytes
- **THEN** the system rejects the request with a 4xx error and stores nothing

#### Scenario: Unauthenticated call rejected
- **WHEN** `secret_put` is called without a valid `mk_agent_` key
- **THEN** the system returns 401 `mintkey:auth_required`

### Requirement: Owning agent can read its secret back in plaintext
The owning agent SHALL be able to read the plaintext value of its own secret via the `secret_get` MCP tool. Every successful plaintext read MUST emit an `agent_secret.read` audit event carrying the secret ID, version, and reader agent ID — never the value. The plaintext value MUST NOT appear in any log line, OTel span attribute, audit payload, or change-event payload.

#### Scenario: Owner reads own secret
- **WHEN** the owning agent calls `secret_get` for a secret it stored
- **THEN** the system returns the plaintext value, name, and version, and emits `agent_secret.read`

#### Scenario: Plaintext never leaks to telemetry
- **WHEN** a secret with a known canary value is stored and read back
- **THEN** grepping service logs, audit event payloads, and exported span attributes for the canary value yields zero matches

### Requirement: Agent can list secrets visible to it
The `secret_list` MCP tool SHALL return metadata (ID, name, version, size, timestamps, access mode `owner` or `shared`) for all secrets the calling agent owns plus all secrets shared with it. It MUST NOT return secret values, and MUST NOT return other agents' unshared secrets even within the same tenant.

#### Scenario: List returns own and shared secrets
- **WHEN** agent B owns one secret and has a share grant on one of agent A's secrets
- **THEN** `secret_list` called by B returns exactly those two entries, marked `owner` and `shared` respectively, with no values

### Requirement: Owning agent can delete its secret
The `secret_delete` MCP tool SHALL allow only the owning agent to delete a secret. Deletion removes the encrypted material and metadata and cascades any share grants. Deletion MUST be idempotent and MUST emit `agent_secret.deleted`.

#### Scenario: Owner deletes a secret with an active share
- **WHEN** the owning agent deletes a secret that is shared with another agent
- **THEN** the secret and its share grants are removed, `agent_secret.deleted` is emitted, and subsequent `secret_get` by the former recipient returns the uniform not-found error

### Requirement: Cross-agent access is denied without enumeration leaks
A secret MUST NOT be readable, modifiable, or deletable by any agent other than its owner (or, for reads, an agent holding a share grant). The error returned for "secret does not exist" and "secret exists but is not visible to you" MUST be indistinguishable (uniform not-found), so agents cannot probe for other agents' secret names or IDs.

#### Scenario: Non-owner read is indistinguishable from missing secret
- **WHEN** agent B calls `secret_get` on agent A's unshared secret, and separately on a random nonexistent ID
- **THEN** both responses have the same status code and error shape

#### Scenario: Recipient cannot write or delete
- **WHEN** an agent holding a read share grant calls `secret_put` (same name) or `secret_delete` on the shared secret
- **THEN** the write targets/creates the recipient's own namespace (put) or returns the uniform not-found error (delete); the owner's secret is unchanged

### Requirement: Tenant isolation under RLS
All new tables (`public.agent_secrets`, `public.agent_secret_grants`, `vault.agent_secrets`) MUST carry `tenant_id UUID NOT NULL` and a `tenant_isolation` RLS policy created in the same Liquibase changeset, referencing `app.current_tenant` with the `platform_admin_view` escape hatch. Cross-tenant access MUST be impossible regardless of application-code bugs.

#### Scenario: RLS coverage gate passes
- **WHEN** the Liquibase changelogs are applied to a fresh Postgres and the RLS architecture test runs with the new tables registered in TENANT_SCOPED
- **THEN** every new table shows `relrowsecurity = true` with a qualifying `tenant_isolation` policy
