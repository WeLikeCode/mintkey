# Tasks — Operator-Provisioned Agent Secrets

Each chunk is dispatched to a Sonnet IMPLEMENTER (test-first, surgical) and independently verified by a fresh Opus REVIEWER. PASS/FAIL/ESCALATE, 3-strike hard-stop.

## 1. Contracts & ADR (land first; validated by repo lint commands)

- [ ] 1.1 Write ADR-0026 `docs/architecture/01-architecture/adr/0026-operator-provisioned-agent-secrets.md` (status Proposed): operator-as-provisioner model, reveal-once is client-side (responses metadata-only), admin-api gains `vault.secret.put`/`.delete`, `agent_secret.created`/`.updated` accept operator actor, new `agent_secrets.created_by`, delete purges ciphertext, S-SEC-1 posture unchanged for operators; references ADR-0025 + ADR-0019. Add `docs/architecture/adrs/0026-…` symlink + index row in `adr/README.md`.
- [ ] 1.2 Extend `docs/architecture/contracts/rest/openapi.yaml`: `POST /v1/tenants/{tenant_id}/agent-secrets` and `PUT /v1/tenants/{tenant_id}/agent-secrets/{secret_id}`; `CreateAgentSecretRequest` (`agent_id`, `name`, `value` with `x-mintkey-sensitive: true`, optional `content_type`) and `UpdateAgentSecretRequest` (`value` + optional `content_type`); metadata-only response schema reuse (AgentSecret); add `name_already_exists` to `x-mintkey-error-codes`; OAS 3.1 nullable style. Verify `openapi-spec-validator` + `redocly lint`.
- [ ] 1.3 Extend `docs/architecture/contracts/events/audit-event.schema.json`: widen `ev_agent_secret_created` and `ev_agent_secret_updated` to allow `actor_type: operator` (keep `agent_secret.read` agent-only); payloads stay identifier/metadata-only. Verify `Draft202012Validator.check_schema`.
- [ ] 1.4 `openspec validate operator-provisioned-agent-secrets --strict` passes (this change's proposal/design/specs/tasks).
- [ ] 1.5 Confirm NO change to `mcp/tools.yaml` or `vault-adapter/vault.proto` (agent surface + vault RPCs already sufficient); add a one-line note in the ADR explaining why.

## 2. Database (Liquibase 028)

- [ ] 2.1 `apps/admin-api/db/changelog/028-agent-secrets-created-by.yaml` registered in `db.changelog-master.yaml`: `addColumn public.agent_secrets.created_by UUID NULL` (no FK required; attribution only), with MARK_RAN precondition + rollback. No RLS change (same table/policy).
- [ ] 2.2 Update the SQLAlchemy mirror for `agent_secrets` in `packages/python/mintkey-models/mintkey_models/db.py`; run `tests/acceptance/test_sqlalchemy_mirror.py`.
- [ ] 2.3 Migrate against fresh testcontainers Postgres; confirm column present and RLS coverage test still green.

## 3. admin-api (Python/FastAPI)

- [ ] 3.1 Add an `AgentSecretsVault` gRPC client to admin-api (model: mcp-server `vault/agent_secrets_client.py` and admin-api `services/vault_client.py`); compose env + `svcid_admin_api` granted `vault.secret.put` + `vault.secret.delete` (vault-adapter identity config + docker-compose env).
- [ ] 3.2 (test-first) `POST /agent-secrets` handler in `apps/admin-api/src/admin_api/api/agent_secrets.py`: resolve operator_id + tenant from session; validate agent-in-tenant, size ≤ 65536, name pattern; reject dup `(tenant,agent,name)` → 409 `name_already_exists`; `PutAgentSecret` (blob-first) then INSERT metadata with `created_by`; emit `agent_secret.created` (operator actor); metadata-only response.
- [ ] 3.3 (test-first) `PUT /agent-secrets/{secret_id}` handler: overwrite via `PutAgentSecret`, `version++`, emit `agent_secret.updated` (operator actor), metadata-only response.
- [ ] 3.4 (test-first) Extend `DELETE` to call `DeleteAgentSecret` (purge blob) in addition to metadata delete; keep idempotent + grant cascade; audit unchanged (operator actor).
- [ ] 3.5 Thread session→operator_id into the agent-secrets handlers; use it for audit `actor_id` + `created_by`; fix the grant-handler `created_by` nil-UUID placeholder (D7 of design doc).
- [ ] 3.6 Regenerate the admin-api `openapi_snapshot.json`; FastAPI↔YAML diff gate must pass.
- [ ] 3.7 Unit tests green (`tests/unit/...` in the CI-executed tree): happy/409/oversize/bad-name/cross-tenant; responses carry no `value`; vault Put/Delete called; operator-actor audit + `created_by`; tenant isolation.

## 4. admin-ui (AdminJS BFF)

- [ ] 4.1 New `agent-secrets` RestResource (`src/resources/agent-secrets.ts`): metadata-only list (name, content_type, size_bytes, version, created_at, updated_at, created_by), filter by `agent_id`; mount in `index.ts`.
- [ ] 4.2 (test-first) Create-form component (`components/actions/AgentSecretNewForm.tsx`) — freeform name/value/content_type → `apiWrite` POST with `operatorOpts` (signed-request) → reveal-once modal rendered client-side from the typed value, cleared on dismiss/unmount.
- [ ] 4.3 Update/rotate action (reveal-once, same pattern) and Delete action (`ConfirmAction`).
- [ ] 4.4 Sharing-grant UI over existing endpoints: create grant (pick recipient agent), list grants, revoke (`ConfirmAction`).
- [ ] 4.5 "Manage secrets" action on the agent show page deep-linking the resource pre-filtered by `agent_id`; register components in `components/index.ts`.
- [ ] 4.6 Ensure the BFF does not log request bodies for these routes.
- [ ] 4.7 vitest green: handler tests (writes use signed-request), render tests (modal shows value once; list/show never render a value), BFF route test (cookie/CSRF forwarded).

## 5. Security gates

- [ ] 5.1 Extend the phase-1 red-team canary test to the operator create/update path; zero matches in logs, span exports, audit payloads.
- [ ] 5.2 Re-run RLS coverage + audit-coverage architecture tests; both green.
- [ ] 5.3 Grep admin-api + admin-ui diff for body/value logging; confirm `value` never placed on an OTel span.

## 6. E2E & finalize

- [ ] 6.1 Backup first (`bash scripts/dev-backup.sh`); bring up an ISOLATED compose project (never `down -v` the shared `mintkey_*` volumes).
- [ ] 6.2 Live e2e: operator `POST` create → agent `secret_get` returns plaintext (access owner) → operator `PUT` rotate (version++) → operator `DELETE` → agent `secret_get` → uniform `secret_not_found`; confirm vault blob absent post-delete.
- [ ] 6.3 Update the agent-secrets-campaign memory with phase 3 (branch, decisions, status).
- [ ] 6.4 Open PR against `main` with the issue-intake summary + verification evidence.
