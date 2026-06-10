# Tasks — Agent-Stored Credentials (Phase 1)

## 1. Contracts & ADR (land first; all validated by repo lint commands)

- [ ] 1.1 Write ADR-0025 `docs/architecture/01-architecture/adr/0025-agent-stored-secrets.md` (status Proposed): plaintext read-back deviation from S-SEC-1 convention, new `sec_`/`secgrant_` prefixes, new audit event types + target types, new error code, MCP-server audit emission point, sharing rule (any tenant operator) + `agents.created_by` rationale; add `docs/architecture/adrs/0025-…` symlink + index entry in `adr/README.md`
- [ ] 1.2 Extend `docs/architecture/contracts/vault-adapter/vault.proto`: new `AgentSecretsVault` service with `PutAgentSecret`/`GetAgentSecret`/`DeleteAgentSecret` (request/response messages keyed tenant_id + secret_id, bytes value); verify with `protoc --descriptor_set_out=/dev/null`
- [ ] 1.3 Extend `docs/architecture/contracts/mcp/tools.yaml`: `secret_put`, `secret_get`, `secret_list`, `secret_delete` (input/output JSON Schemas draft 2020-12, additionalProperties false, `x-mintkey-sensitive: true` on plaintext value output, scopes `write:secrets`/`read:secrets`/`delete:secrets`, errors from closed enum, `$defs/secret_id` pattern, ID-prefix comment block update); verify `yaml.safe_load`
- [ ] 1.4 Extend `docs/architecture/contracts/rest/openapi.yaml`: tag AgentSecrets; paths `/v1/tenants/{tenant_id}/agent-secrets` (GET list metadata), `/{secret_id}` (GET metadata, DELETE), `/{secret_id}/grants` (POST, GET), `/{secret_id}/grants/{grant_id}` (DELETE 204 idempotent); components AgentSecret/AgentSecretGrant/CreateAgentSecretGrantRequest (prefixed-ULID IDs, OAS 3.1 nullable style); SecretId parameter; prefix-table rows; AuditEventType + TargetType enum additions; `x-mintkey-error-codes` addition; verify openapi-spec-validator + redocly lint
- [ ] 1.5 Extend `docs/architecture/contracts/events/audit-event.schema.json`: 6 `ev_agent_secret_*` $defs (allOf envelope, const event_type/target_type, closed identifier-only payloads), oneOf + discriminator.mapping entries, `agent_secret`/`agent_secret_grant` target_type enum values, `$defs/secret_id`; verify Draft202012Validator.check_schema

## 2. Database (Liquibase 027)

- [ ] 2.1 `apps/admin-api/db/changelog/027-agent-secrets.yaml` registered in `db.changelog-master.yaml`: `public.agent_secrets` (id UUID PK, tenant_id FK, agent_id FK, name, content_type, size_bytes, version, timestamps, UNIQUE(tenant_id, agent_id, name)), `public.agent_secret_grants` (id, tenant_id, secret_id FK ON DELETE CASCADE, recipient_agent_id FK, created_by, created_at, UNIQUE(tenant_id, secret_id, recipient_agent_id) named uq_agent_secret_grants), `vault.agent_secrets` (secret_id PK, tenant_id, key_version, wrapped_dek, enc_payload, timestamps), `agents.created_by UUID NULL` addColumn; per table: tenant index, ENABLE RLS + `tenant_isolation` policy (current_tenant + platform_admin_view) in same file, GRANT to mintkey_app; MARK_RAN preconditions + rollbacks
- [ ] 2.2 SQLAlchemy mirror models in `packages/python/mintkey-models/mintkey_models/db.py` for the two public tables (+ vault table if mirror test requires); run `tests/acceptance/test_sqlalchemy_mirror.py`
- [ ] 2.3 Register `agent_secrets`, `agent_secret_grants` (and vault table if applicable) in `tests/architecture/test_rls_coverage.py` TENANT_SCOPED; run the test locally against testcontainers Postgres — must pass

## 3. Vault-adapter (Go)

- [ ] 3.1 Regenerate Go stubs (`make proto-gen`) and Python client stubs for the new RPCs
- [ ] 3.2 Implement `AgentSecretsVault` gRPC service: Seal/Open via existing crypto, Postgres store ops with `set_config('app.current_tenant')` + advisory lock, sqlite backend parity or explicit unsupported error; register in grpc.go with methodScopes `vault.secret.put/read/delete`; add `svcid_mcp` boot identity in cmd/vault-adapter/main.go + compose env wiring
- [ ] 3.3 Go tests: table-driven service tests (-short) + `//go:build postgres` store tests with RLS assertions via MINTKEY_TEST_PG_APP_DSN; `go test ./... -short` green

## 4. MCP server tools (agent data plane)

- [ ] 4.1 gRPC client for AgentSecretsVault in mcp-server (model: admin-api `services/vault_client.py`); compose env VAULT_GRPC_ADDR + identity/token for svcid_mcp
- [ ] 4.2 `tools/secret_put.py`: 401 guard → set_tenant_context → name validation + 64KiB limit → upsert metadata + PutAgentSecret (blob-first) → version bump → `agent_secret.created`/`.updated` audit → wire-ID response; distinct SQL bind-param names to avoid test-mock collisions
- [ ] 4.3 `tools/secret_get.py`: owner-or-grant check (single SQL), uniform not-found otherwise; GetAgentSecret unseal; `agent_secret.read` audit in same transaction; plaintext only in response body
- [ ] 4.4 `tools/secret_list.py`: metadata-only union of owned + granted with access_mode flag; no values
- [ ] 4.5 `tools/secret_delete.py`: owner-only, uniform not-found otherwise; delete blob + metadata (grants cascade); idempotent; `agent_secret.deleted` audit
- [ ] 4.6 Register all four: main.py routers (NOT in auth-bypass list), landing.py `_REST_ENDPOINTS`+`_TOOLS_INDEX`, jsonrpc.py TOOLS + `_dispatch_tool` (do not repeat the email-tools gap), `utils/wire_ids.py` `sec_` prefix + resolve helper (sync both copies), `skills/agent-bootstrap.md` section
- [ ] 4.7 Unit tests `apps/mcp-server/tests/test_secret_tools.py` per email pattern covering every storage-spec scenario incl. anti-enumeration equality assertion; add CI step so mcp-server tests actually run

## 5. Admin API (operator sharing plane)

- [ ] 5.1 `api/agent_secrets.py` router: list/get metadata (never values), grants POST/GET/DELETE per email_permission_grants pattern (set_tenant_context, dual-form ID decode, in-tenant FK validation 422, dup 409, idempotent DELETE 204, audit_emit + notify_change identifiers-only); reject grant-to-owner; register in main.py; populate `agents.created_by` in agent creation handler
- [ ] 5.2 Update `tests/acceptance/openapi_snapshot.json`; unit tests `tests/unit/admin_api/test_agent_secrets.py` (repo-root tree, CI-executed) covering every sharing-spec scenario; audit-coverage gate passes
- [ ] 5.3 Run contract parity: FastAPI emitted spec vs canonical openapi.yaml diff clean

## 6. Security gates & red-team

- [ ] 6.1 Acceptance gate `tests/acceptance/test_no_plaintext_in_secret_audit.py` (AST: secret tool modules never pass value-bearing names into audit_emit/notify/span calls)
- [ ] 6.2 Canary red-team test: store canary via live stack, read back, grep compose logs + audit_events payloads + span exports for canary — zero matches (model: email leak_redteam + scripts/red-team-fingerprints.txt)

## 7. End-to-end (live stack, isolated volumes)

- [ ] 7.1 Extend `scripts/e2e_smoke.py` + ENDPOINT_COVERAGE.md with agent-secrets steps; golden-path-style integration test: agent A store → A read → operator grant to B → B read → B list shows shared → revoke → B read uniform-404 → A delete → idempotent re-delete
- [ ] 7.2 Run full suite locally: make test (unit+arch+acceptance), go test ./... -short, RLS coverage test, live e2e on isolated compose project — all green with outputs captured

## 8. Finalize

- [ ] 8.1 Update `docs/HOW-TO.md` (new §: agent-stored secrets) + CLAUDE.md pattern-library row
- [ ] 8.2 PR with intake stub, CI green, reviewer findings addressed, merge
