# Agent Secret Provisioning

## ADDED Requirements

### Requirement: Operator can provision a secret into an agent's namespace
An authenticated tenant operator SHALL be able to create a secret owned by a target agent via `POST /v1/tenants/{tenant_id}/agent-secrets` with body `{ agent_id, name, value, content_type? }`. The target agent MUST exist in the operator's tenant. The `value` MUST be at most 65536 bytes and `name` MUST match `^[A-Za-z0-9._-]{1,128}$`. The value MUST be envelope-encrypted (AES-256-GCM DEK wrapped by the process KEK) via `PutAgentSecret` and stored in `vault.agent_secrets`; metadata MUST be written to `public.agent_secrets` with `agent_id` = the target agent and `created_by` = the operator. The operation MUST emit `agent_secret.created` with `actor_type: operator`. The response MUST be metadata-only.

#### Scenario: Successful provision
- **WHEN** an operator POSTs a valid `{agent_id, name, value}` for an agent in their tenant
- **THEN** a `sec_…` secret is created owned by that agent, the ciphertext is stored in `vault.agent_secrets`, `agent_secret.created` is emitted with the operator as actor, and the 201 response contains metadata only (id, name, version, size_bytes, content_type, created_at) with no `value` field

#### Scenario: Duplicate name rejected
- **WHEN** an operator POSTs a `name` that already exists for that `(tenant_id, agent_id)`
- **THEN** the request returns `409 name_already_exists`, no vault write occurs, and no audit event is emitted

#### Scenario: Oversize or malformed input rejected
- **WHEN** an operator POSTs a `value` larger than 65536 bytes or a `name` not matching the allowed pattern
- **THEN** the request returns `422` and no secret is created

#### Scenario: Cross-tenant agent rejected
- **WHEN** an operator references an `agent_id` that does not exist in the path tenant
- **THEN** the request is rejected with `422 not_found` and no secret is created

### Requirement: Operator can update/rotate a provisioned secret's value
An authenticated tenant operator SHALL be able to replace an existing secret's value via `PUT /v1/tenants/{tenant_id}/agent-secrets/{secret_id}` with body `{ value, content_type? }`. The new value MUST be envelope-encrypted and overwrite the ciphertext; the metadata `version` MUST increment. The operation MUST emit `agent_secret.updated` with `actor_type: operator`. The response MUST be metadata-only.

#### Scenario: Rotation increments version and reveals nothing
- **WHEN** an operator PUTs a new value for an existing secret at version N
- **THEN** the stored ciphertext is replaced, the metadata version becomes N+1, `agent_secret.updated` is emitted with the operator as actor, and the response contains metadata only with no `value` field

### Requirement: A provisioned secret is owned by the target agent and readable via secret_get
A secret created by an operator for an agent SHALL be indistinguishable, on the agent surface, from one the agent stored itself: the owning agent reads its plaintext via the existing `secret_get` tool with `access: owner`. This change MUST NOT alter the agent MCP surface (`mcp/tools.yaml`) or the vault proto.

#### Scenario: Agent reads an operator-provisioned secret
- **WHEN** the target agent calls `secret_get` with the provisioned secret's ID
- **THEN** the plaintext value the operator entered is returned with `access: owner`, and `agent_secret.read` is emitted with the agent as the reading actor

### Requirement: Operator-facing responses never carry plaintext (reveal-once is client-side)
No admin-api endpoint may return an agent secret's plaintext value or ciphertext, including the create and update responses. The Admin UI MAY display the value the operator just entered exactly once (reveal-once), rendered client-side from the submitted form and discarded on dismissal; it MUST NOT fetch a stored value from the server.

#### Scenario: Create response contains no value
- **WHEN** an operator creates or updates a secret
- **THEN** the admin-api response body contains metadata fields only, with no `value`, ciphertext, or key-material field present

#### Scenario: UI reveals the entered value once
- **WHEN** the create form submits successfully
- **THEN** the UI shows the value the operator typed exactly once with a copy affordance and discards it on dismissal, and no subsequent UI view re-displays a stored value

### Requirement: Operator delete purges ciphertext
Operator deletion via `DELETE /v1/tenants/{tenant_id}/agent-secrets/{secret_id}` SHALL remove both the `public.agent_secrets` metadata row and the `vault.agent_secrets` ciphertext blob (via `DeleteAgentSecret`), cascade share grants, be idempotent (204), and emit `agent_secret.deleted` with `actor_type: operator` when a row was actually removed.

#### Scenario: Delete removes ciphertext and metadata
- **WHEN** an operator deletes a provisioned secret
- **THEN** the metadata row and the vault ciphertext blob are both removed, grants are cascaded, `agent_secret.deleted` is emitted with the operator as actor, and a subsequent `secret_get` by the owning agent returns the uniform `secret_not_found`

### Requirement: Operator writes require signed-request authentication
Every operator state-changing call in this surface (create, update, delete, grant create/revoke) MUST require both the `mintkey_session` cookie and a valid Ed25519 `x-mintkey-signed-request` whose claims agree with the session (`sub == operator_id`, `tnt == tenant_id`), per ADR-0019. The effective identity used for the tenant context GUC, the audit `actor_id`, and `created_by` MUST come from the session, not the JWT body.

#### Scenario: Missing signed request is rejected
- **WHEN** a create/update/delete request arrives with a valid session cookie but no valid `x-mintkey-signed-request`
- **THEN** the request is rejected and no state changes

### Requirement: Zero plaintext in logs, audit, and telemetry on the operator path
The provisioned `value` MUST NOT appear in any admin-api or admin-ui log line, audit payload, or OTel span attribute. Audit payloads for `agent_secret.created`/`.updated`/`.deleted` MUST carry identifiers and metadata only.

#### Scenario: Canary value does not leak
- **WHEN** an operator provisions a secret containing a known canary value and the system processes create, read, rotate, and delete
- **THEN** the canary value appears in zero log lines, zero span exports, and zero audit payloads
