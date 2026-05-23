# Issue Intake — r4-pin-remaining-images

## Problem statement

DSBR session identified 8 `docker-compose.yml` services with tag-only image references (no `@sha256:` digest). Evidence ledger entries `EV-COMPOSE-002` and `EV-COMPOSE-003` list these as open gap `EV-GAP-006`. Without pinned digests, `docker compose up` can silently pull a different image layer if the registry tag is overwritten — the same failure mode that caused the 2026-05-18 dev-data wipe (unpinned `postgres:16`).

## User-visible symptom

Running `grep -nE '^\s*image:' docker-compose.yml` shows 8 of the 9 non-built service images without a `@sha256:` suffix:
- `quay.io/keycloak/keycloak:24.0`
- `liquibase/liquibase:4.27.0`
- `kong:3.6`
- `otel/opentelemetry-collector-contrib:0.104.0`
- `jaegertracing/all-in-one:1.56`
- `prom/prometheus:v2.51.0`
- `gcr.io/cadvisor/cadvisor:v0.49.1`
- `grafana/grafana:10.3.3`

## Expected behavior

Every `image:` line in `docker-compose.yml` includes an `@sha256:<digest>` suffix anchoring it to the exact manifest list that was tested. `grep -nE '^\s*image:' docker-compose.yml | grep -v '@sha256:'` must produce only build-context services (no `image:` lines).

## Evidence

- `EV-COMPOSE-002` / `EV-COMPOSE-003` in DSBR evidence ledger
- `docker-compose.yml` lines 57, 86, 335, 456, 473, 549, 566, 587 (pre-fix) — all tag-only

## Scope

- `docker-compose.yml` (8 `image:` lines only)
- `team/remediation/2026-05-18-r4-pin-remaining-images/{ISSUE_INTAKE.md, BASE_IMAGE_LOCK.md, 99-report.md}`

## Out of scope

All Dockerfiles, source code, go.mod, pyproject.toml, CI workflows, or any other file not listed in Scope above.

## Risk level

`security / availability` — unpinned images are a supply-chain integrity risk and reproducibility hazard.

## Verification target

```bash
cd /Users/alexandruiacobescu/gooseProjects/mintkey-r4-pin-remaining-images
grep -nE '^\s*image:' docker-compose.yml | head -20
python3 -c "import yaml; d=yaml.safe_load(open('docker-compose.yml')); print('YAML OK')"
docker compose config --quiet && echo "compose-config OK"
```

Every `image:` line for a non-built service must contain `@sha256:`. YAML parse and `compose config` must succeed with no errors.

## Owner decisions noted

- Use the manifest-list (top-level) digest from `docker buildx imagetools inspect`, not a platform-specific digest — matches the postgres precedent.
- Preserve existing tags verbatim; only append `@sha256:<digest>`.
- No stack restart; pins take effect on next `docker compose up` or explicit pull.
