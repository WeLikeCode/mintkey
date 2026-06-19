# Backend Migration

## ADDED Requirements

### Requirement: Agent secrets can be migrated from Postgres to HashiCorp Vault

An operator SHALL be able to migrate all agent secrets from the Postgres backend to a HashiCorp Vault KV v2 backend using `make migrate-agent-secrets-pg-to-hv`, following the pattern established by `make migrate-vault-sqlite-to-pg` (ADR-0021). The migration MUST be: idempotent (re-running produces no duplicate secrets, skip-on-conflict); non-destructive (Postgres rows are NOT deleted during migration); and verified (a post-migration probe reads back a sample of migrated secrets from the new backend and asserts byte-equality of the encrypted blob).

Migration semantics are hard cutover: after the migration completes and the operator sets `MINTKEY_AGENT_SECRET_BACKEND=hashicorp-vault` and restarts vault-adapter, new requests use Vault exclusively. There is no dual-read transition window in this phase (it would require the vault-adapter to query two backends per request, adding latency and complexity — deferred). The Postgres rows remain as a rollback safety net; rollback is `MINTKEY_AGENT_SECRET_BACKEND=postgres` + service restart.

#### Scenario: Migrate all agent secrets from Postgres to Vault — idempotent
- **WHEN** `make migrate-agent-secrets-pg-to-hv` is run twice
- **THEN** both runs exit 0; the second run reports "N secrets already present, skipped"; no duplicate paths exist in the Vault KV mount

#### Scenario: Migration verification probe asserts byte equality
- **WHEN** the migration completes
- **THEN** the migration tool reads back a random 5-secret sample from the Vault KV backend and asserts that the `enc_payload` bytes match the source Postgres rows exactly; any mismatch causes the tool to exit non-zero and print the mismatched `secret_id`

#### Scenario: Postgres rows are retained after migration
- **WHEN** `make migrate-agent-secrets-pg-to-hv` completes successfully
- **THEN** the `vault.agent_secrets` table in Postgres is unchanged (no rows deleted); the operator must explicitly DROP or truncate the table if cleanup is desired

---

### Requirement: Agent secrets can be migrated from Postgres to Azure Key Vault

An operator SHALL be able to migrate all agent secrets from the Postgres backend to an Azure Key Vault backend using `make migrate-agent-secrets-pg-to-akv`. The same idempotency, non-destructivity, and verification semantics as the Postgres-to-HashiCorp-Vault migration apply.

#### Scenario: Migrate all agent secrets from Postgres to Azure KV — idempotent
- **WHEN** `make migrate-agent-secrets-pg-to-akv` is run twice
- **THEN** both runs exit 0; the second run reports "N secrets already present, skipped" (Azure KV `PUT` with `content_type` and `tags` matching the existing secret returns 200 OK; the migration tool treats 200 on an existing name as "already present")

#### Scenario: Migration verification probe asserts byte equality (Azure KV)
- **WHEN** the Postgres-to-Azure-KV migration completes
- **THEN** the migration tool reads back a random 5-secret sample from Azure Key Vault, decodes the base64 blob, and asserts byte equality with the source Postgres `enc_payload`; any mismatch causes exit non-zero

---

### Requirement: Rollback to Postgres is a config-only restart

An operator SHALL be able to roll back from an external backend to Postgres at any time by unsetting `MINTKEY_AGENT_SECRET_BACKEND` (or setting it to `postgres`) and restarting vault-adapter. Secrets written to the external backend after the migration cutover and before rollback will NOT be available in Postgres (they were written to the external backend). The migration tool MUST document this gap in its `--help` output. Bi-directional migration (external backend → Postgres) is out of scope for this phase.

#### Scenario: Setting MINTKEY_AGENT_SECRET_BACKEND=postgres reverts to Postgres backend
- **WHEN** vault-adapter is restarted with `MINTKEY_AGENT_SECRET_BACKEND=postgres` after having been run with `hashicorp-vault`
- **THEN** all agent-secret operations use the Postgres store; secrets that existed in Postgres before the migration are accessible; secrets written to Vault after cutover are not accessible (expected and documented)

#### Scenario: Migration tool --help documents rollback gap
- **WHEN** `migrate-agent-secrets --help` is run
- **THEN** the output contains a warning that secrets written to the external backend after cutover will not be visible after rollback to Postgres
