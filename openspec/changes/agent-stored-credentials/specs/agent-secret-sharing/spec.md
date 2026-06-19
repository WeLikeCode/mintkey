# Agent Secret Sharing

## ADDED Requirements

### Requirement: Operator can grant read-only access to another agent
An authenticated tenant operator SHALL be able to create a share grant giving a recipient agent read-only access to an existing secret, via `POST /v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants`. The secret and the recipient agent MUST both exist in the operator's tenant (cross-tenant references are rejected). Duplicate grants (same secret, same recipient) MUST return 409. The grant MUST emit `agent_secret_grant.created` with operator actor attribution. Granting a secret to its own owner MUST be rejected.

#### Scenario: Successful share grant
- **WHEN** an operator grants agent B read access to agent A's secret
- **THEN** the grant row is created, `agent_secret_grant.created` is emitted with the operator as actor, and agent B's subsequent `secret_get` on that secret returns the plaintext value

#### Scenario: Cross-tenant grant rejected
- **WHEN** an operator references a secret or recipient agent that does not exist in the path tenant
- **THEN** the request is rejected with 422 `not_found` and no grant is created

#### Scenario: Duplicate grant rejected
- **WHEN** an operator creates a grant identical to an existing one
- **THEN** the request returns 409 `already_exists`

### Requirement: Recipient reads are plaintext, read-only, and audited
An agent holding a share grant SHALL read the shared secret's plaintext via the same `secret_get` tool it uses for its own secrets. Each such read MUST emit `agent_secret.read` identifying the reader as the recipient. Share grants confer read only: no update, no delete, no re-share.

#### Scenario: Recipient reads shared secret
- **WHEN** agent B (grant holder) calls `secret_get` with the shared secret's ID
- **THEN** the plaintext value is returned and `agent_secret.read` is emitted with agent B as the reading actor

### Requirement: Operator can list and revoke share grants
Operators SHALL be able to list grants for a secret and revoke a grant via `DELETE`. Revocation MUST be idempotent, MUST take effect immediately (the next `secret_get` by the former recipient returns the uniform not-found error), and MUST emit `agent_secret_grant.revoked` when a grant row was actually removed.

#### Scenario: Revocation takes immediate effect
- **WHEN** an operator revokes agent B's grant and agent B then calls `secret_get`
- **THEN** the call returns the uniform not-found error and `agent_secret_grant.revoked` was emitted

#### Scenario: Idempotent revoke
- **WHEN** an operator deletes a grant that was already deleted
- **THEN** the response is successful (204); no audit event is emitted because no state changed (the schema-required grant identifiers are unknowable once the row is gone)

### Requirement: Operator can delete an agent secret
As tenant administrators, operators SHALL be able to hard-delete any agent secret in their tenant via `DELETE /v1/tenants/{tenant_id}/agent-secrets/{secret_id}` (e.g. when offboarding an agent or responding to a leak). Deletion removes ciphertext and metadata, cascades share grants, is idempotent (204), and MUST emit `agent_secret.deleted` with operator actor attribution.

#### Scenario: Operator deletes an agent's secret
- **WHEN** an operator deletes agent A's secret that is shared with agent B
- **THEN** the secret and its grants are removed, `agent_secret.deleted` is emitted with the operator as actor, and subsequent `secret_get` by A or B returns the uniform not-found error

### Requirement: Operators never see secret values
The operator REST surface SHALL expose secret metadata (ID, name, owner agent, version, size, timestamps) and grants only. No admin-api endpoint may return an agent secret's plaintext or ciphertext.

#### Scenario: Metadata listing contains no values
- **WHEN** an operator lists a tenant's agent secrets
- **THEN** the response contains metadata fields only, with no value, ciphertext, or key material fields present
