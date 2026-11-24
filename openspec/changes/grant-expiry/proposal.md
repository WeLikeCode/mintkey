# A permission grant can expire and records who gave it

## Why

A permission grant lives until someone deletes it, and its `created_by` is whatever the request body said or the
grantee's own id. Two things the next changes need are missing. Time-boxed access: an agent that lets another agent use
a service, or an operator who approves a request, must be able to say "until Friday", and the broker must stop issuing
tokens when that time passes. And a trustworthy grantor: the record must say whether an operator or an agent gave the
grant, and who, taken from the authenticated caller and never from the body. `time_window` is a recurring weekday and
hours window, not an expiry, so neither exists.

## What Changes

- Liquibase `030-grant-expiry.yaml`: `permission_grants.expires_at` (TIMESTAMPTZ, null = no expiry), `grantor_type`
  (`operator` | `agent`, default `operator`) and `grantor_id` (UUID, null for existing rows).
- Two modules give the write path to every caller: `admin_api.services.grant_expiry` (the expiry rules and the reader of
  `MINTKEY_AGENT_GRANT_MAX_TTL`: default 7 days, ceiling 90 days) and `admin_api.services.grants` (`write_grant`,
  `delete_grant`, the audit and NOTIFY payload builders, `grant_wire_fields`). The operator's grant route uses them, so
  `granted_by` in a body is ignored and the grantor is the operator of the session.
- The operator API accepts `expires_at` on a grant, answers `expires_at`, `expired`, `grantor_type` and `grantor_id` on
  every grant it returns, and the tenant grant list takes a `grantor_agent_id` filter. A live grant ends early or is
  renewed only by revoking it: the same agent, service and action with another expiry answers 409; an expired grant is
  replaced by granting again.
- An expired grant is absent for the agent: `request_token` answers 403 `grant_expired` and writes `token.denied`;
  `mintkey_list_services`, `mintkey_discover` and `mintkey_describe_service` do not show it; the classical API key
  creation and the agent grant counts ignore it.
- A token lives `min(600 s, the seconds until expires_at)`; below 5 s the token is refused.
- The audit contract records the grantor and the expiry on `agent.permission.granted` and `.revoked` and lists the
  reason `grant_expired`.

## Capabilities

### New Capabilities
- `grant-expiry`: a grant's expiry and grantor, the shared write path, and how an expired grant is treated.

## Impact

- Changed: `apps/admin-api/src/admin_api/api/permissions.py`, `apps/admin-api/src/admin_api/api/agents.py`,
  `apps/admin-api/src/admin_api/api/api_keys.py`, `apps/admin-api/src/admin_api/db/tables.py`,
  `apps/mcp-server/src/mcp_server/tools/request_token.py`, `apps/mcp-server/src/mcp_server/tools/discovery.py`,
  `docs/architecture/contracts/events/audit-event.schema.json`, `apps/admin-api/db/changelog/db.changelog-master.yaml`.
- New: `apps/admin-api/db/changelog/030-grant-expiry.yaml`, `apps/admin-api/src/admin_api/services/grant_expiry.py`,
  `apps/admin-api/src/admin_api/services/grants.py`, `apps/mcp-server/src/mcp_server/policy/grant_expiry.py`.
- New tests: `tests/unit/admin_api/test_grant_expiry_migration.py`, `tests/unit/admin_api/test_grant_expiry_rules.py`,
  `tests/unit/admin_api/test_grants_service.py`, `tests/unit/admin_api/test_permissions_expiry.py`,
  `tests/unit/admin_api/test_grant_expiry_readers.py`, `tests/unit/admin_api/test_audit_schema_grants.py`,
  `apps/mcp-server/tests/test_grant_expiry_tokens.py`, `apps/mcp-server/tests/test_grant_expiry_discovery.py`.
- Changed existing test (set-up only): `tests/unit/admin_api/test_permissions.py::test_revoke_returns_204_and_notifies`.
- Operators: run the migration with the release. Existing grants have no expiry and `grantor_type` `operator`; nothing
  changes for them. A new request field and new response fields are additive.
- Out of scope: email grants, long-lived service API keys already issued, an expiry change on an existing grant
  (revoke and grant again), the proxy's handling of a revoked grant's tokens, any agent-side grant route.
- Plan order: this change merges before `agent-roles-and-ownership` (both append to `db.changelog-master.yaml` and
  `audit-event.schema.json`), and `revoke_permission` is also on the path of the proxy's revocation change.
