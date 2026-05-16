# Issue Intake — 2026-05-17-seed-job-perms

**Session:** `2026-05-17-seed-job-perms`
**Date:** 2026-05-17
**Owner:** SEED-JOB-PERMS implementer subagent

---

## Problem statement (required)

The CI `Integration Tests` job fails because `docker compose up -d` runs the `seed-job` one-shot init container, which exits with code 1. The seed-job container runs as UID 65532 (set by `USER 65532:65532` in `seed-job/Dockerfile`, introduced in PR #33 REL-3), but the `bootstrap_secrets` Docker named volume is owned by root. UID 65532 has no write permission on that directory, so every attempt to write a secret file raises `PermissionError: [Errno 13] Permission denied`.

## User-visible symptom (required)

CI `Integration Tests` job fails. `docker compose logs seed-job` shows:

```
seed-job-1  | PermissionError: [Errno 13] Permission denied: '/run/secrets/mintkey/bootstrap-secrets/admin_password'
seed-job-1  | PermissionError: [Errno 13] Permission denied: '/run/secrets/mintkey/bootstrap-secrets/oidc_client_secret'
```

All downstream services that `depends_on: seed-job` with `condition: service_completed_successfully` also fail to start.

## Expected behavior (required)

seed-job writes all secret files into `/run/secrets/mintkey/bootstrap-secrets/`, exits 0, and all downstream services start normally.

## Evidence (required)

- `seed-job/Dockerfile:19` — `USER 65532:65532` directive (introduced PR #33)
- `docker-compose.yml` — `seed-job` mounts `bootstrap_secrets:/run/secrets/mintkey/bootstrap-secrets` (read-write, no uid option)
- Docker named volumes are created root-owned by the Docker daemon; named volumes do not support per-mount uid options
- `seed-job/main.py:30` — `BOOTSTRAP_SECRETS_DIR = Path(os.getenv("BOOTSTRAP_SECRETS_DIR", "./data/bootstrap-secrets"))` — seed-job writes to this directory
- `seed-job/main.py:447,453,455,467,614,767` — chmod calls set 0o640/0o644/0o600/0o400 per file for downstream reader compatibility

## Scope (required)

`seed-job/Dockerfile` only. No other files require changes.

## Out of scope (required)

- `admin-api/`, `mcp-server/`, `services/` — product code, MUST NOT touch
- Other containers' USER directives
- `seed-job/main.py` chmod logic — MUST be preserved (downstream containers depend on it)
- `docker-compose.yml` volume definitions

## Risk level (required)

CI (blocker — Integration Tests cannot pass without this fix).

## Verification target (required)

```
docker compose down -v
docker compose build seed-job
docker compose up -d
docker compose logs seed-job | tail -20
# Expect: seed-job exits 0, no PermissionError
docker compose ps
# Expect: seed-job shows Exited(0), all other services running
```

If Docker unavailable locally: push branch, CI `Integration Tests` must pass.

## Owner decisions needed (if any)

None. Option B (revert to root) selected per implementer authority; rationale documented in Dockerfile.

---

## Checklist (orchestrator may not start without all required fields)

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line references)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (none)
