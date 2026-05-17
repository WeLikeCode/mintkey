# Issue Intake — s2-trivy-base-image-bump

## Problem statement

~750 open Trivy alerts across the five Mintkey container images (`mintkey-admin-api`, `mintkey-mcp-server`, `mintkey-admin-ui`, `mintkey-seed-job`, `mintkey-mock-backend`) trace to Debian-base CVEs that propagate from shared base images. The `mock-backend` and `seed-job` Dockerfiles pin `python:3.12-slim` (generic slim alias) rather than the explicit `python:3.12-slim-bookworm` tag; the explicit bookworm tag has a newer digest with patched OS packages.

## User-visible symptom

GitHub Code Scanning / Trivy container-scan job reports ~750 CRITICAL/HIGH findings including:
- CVE-2026-31789 (4×) in admin-api + mcp-server
- CVE-2023-45853 (3×) in admin-api + admin-ui + mcp-server
- CVE-2026-42010 (3×), CVE-2026-33845 (3×)
- CVE-2026-0861 (6× high), CVE-2026-28387/8/9/90 (16× high)

## Expected behavior

All Dockerfiles pinned to the latest `@sha256:` digest of the correct explicit tag family (`python:3.12-slim-bookworm`, `node:22-bookworm-slim`, `golang:1.26-alpine`). CVE count drops by ~750 on re-scan.

## Evidence

- `mock-backend/Dockerfile:4` — `FROM python:3.12-slim@sha256:401f6e1a...` (generic tag, older digest)
- `seed-job/Dockerfile:3` — `FROM python:3.12-slim@sha256:401f6e1a...` (generic tag, older digest)
- `python:3.12-slim-bookworm` registry digest `sha256:d193c6f5...` contains patched Debian bookworm packages
- All other base images confirmed current via `docker pull` + registry API on 2026-05-18

## Scope

Only `FROM` lines in every Dockerfile under the repo. `team/remediation/2026-05-18-s2-trivy-base-image/` docs. No source code, no runtime config.

## Out of scope

Any Python/Go/Node/JS source code, pyproject.toml, uv.lock, package.json, pnpm-lock.yaml, go.mod, requirements.txt, or any other non-Dockerfile file.

## Risk level

`security` — CVE remediation. Low blast radius for the image build; no source change.

## Verification target

```bash
find . -name 'Dockerfile' | xargs grep '^FROM' | grep -v '@sha256:' # must produce no output
docker compose build 2>&1 | tail -5
docker compose up -d --wait && docker compose ps
curl -sf http://localhost:8080/v1/health
curl -sf http://localhost:8082/v1/health
```

## Owner decisions noted

Owner-locked: stay on `python:3.12-slim-bookworm` / `node:22-bookworm-slim` / `golang:1.22-bookworm` tag family. Bump tag + repin SHA. Do NOT migrate to distroless or alpine.
