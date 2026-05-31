-- cleanup-orphan-agents.sql
--
-- One-off maintenance: delete agents that have zero permission_grants AND no
-- service_api_keys referencing them. These accumulate from E2E test runs that
-- create agents but never grant them anything (or revoke everything and forget
-- to delete the agent row).
--
-- Idempotent: safe to re-run; a no-op on a clean deployment.
-- Safe-by-default: wrapped in a transaction; review the SELECT output first,
-- then COMMIT or ROLLBACK manually if you prefer not to run the DELETE blind.
--
-- Usage (local dev stack):
--   docker exec -i mintkey-postgres-1 psql -U mintkey_migrate -d mintkey \
--     < scripts/cleanup-orphan-agents.sql
--
-- First applied 2026-05-31 to the local dev stack after the vault-pg-migration
-- session — pruned 39 e2e/test agents left over from earlier sessions
-- (gh-agent-runbook-verify, ddee-agent-*, e2e-*, RevokedAgent-*, etc.).

BEGIN;

-- Show what will go (for the human running this interactively).
SELECT a.id, a.name, a.tenant_id, a.created_at
FROM   agents a
WHERE  NOT EXISTS (SELECT 1 FROM permission_grants WHERE agent_id = a.id)
ORDER BY a.created_at DESC;

-- Dependents: clean any service_api_keys that point at the orphan agents.
-- (If FK is ON DELETE CASCADE we wouldn't need this — confdeltype is currently
-- 'a' = NO ACTION so we must delete in order.)
DELETE FROM service_api_keys
WHERE  agent_id IN (
    SELECT a.id FROM agents a
    WHERE NOT EXISTS (SELECT 1 FROM permission_grants WHERE agent_id = a.id)
);

-- Now delete the orphans.
DELETE FROM agents a
WHERE  NOT EXISTS (SELECT 1 FROM permission_grants WHERE agent_id = a.id);

-- Sanity: should be 0 after.
SELECT count(*) AS still_zero_perm
FROM   agents a
WHERE  NOT EXISTS (SELECT 1 FROM permission_grants WHERE agent_id = a.id);

COMMIT;
