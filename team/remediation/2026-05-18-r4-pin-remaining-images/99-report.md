# Session Close Report — R-4 Pin Remaining Compose Images

**Branch:** `fix/r4-pin-remaining-images-2026-05-18`
**Date:** 2026-05-18
**Closes:** EV-GAP-006 (ledger EV-COMPOSE-002 + EV-COMPOSE-003)

---

## Summary

Pinned all 8 tag-only `image:` references in `docker-compose.yml` to `@sha256:` manifest-list digests retrieved via `docker buildx imagetools inspect`. Each line now has the format `<image>:<tag>@sha256:<digest>`, matching the postgres convention from PR #70. No tags were altered. YAML parse and `docker compose config --quiet` both pass cleanly.

---

## Image pin table

| Service | Old (tag-only) | Digest appended | Source |
|---|---|---|---|
| `keycloak` | `quay.io/keycloak/keycloak:24.0` | `@sha256:f8ade94c…` | `docker buildx imagetools inspect quay.io/keycloak/keycloak:24.0` |
| `liquibase` | `liquibase/liquibase:4.27.0` | `@sha256:141a9fb5…` | `docker buildx imagetools inspect liquibase/liquibase:4.27.0` |
| `kong` | `kong:3.6` | `@sha256:a42d2b45…` | `docker buildx imagetools inspect kong:3.6` |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.104.0` | `@sha256:e07e325e…` | `docker buildx imagetools inspect otel/opentelemetry-collector-contrib:0.104.0` |
| `jaeger` | `jaegertracing/all-in-one:1.56` | `@sha256:d2cd4c22…` | `docker buildx imagetools inspect jaegertracing/all-in-one:1.56` |
| `prometheus` | `prom/prometheus:v2.51.0` | `@sha256:5ccad477…` | `docker buildx imagetools inspect prom/prometheus:v2.51.0` |
| `cadvisor` | `gcr.io/cadvisor/cadvisor:v0.49.1` | `@sha256:3cde6faf…` | `docker buildx imagetools inspect gcr.io/cadvisor/cadvisor:v0.49.1` |
| `grafana` | `grafana/grafana:10.3.3` | `@sha256:8640e503…` | `docker buildx imagetools inspect grafana/grafana:10.3.3` |

---

## Verification output

```
$ grep -nE '^\s*image:' docker-compose.yml | head -20
36:    image: postgres:16@sha256:b6ccf02e9b47...
60:    image: quay.io/keycloak/keycloak:24.0@sha256:f8ade94c1d0a...
91:    image: liquibase/liquibase:4.27.0@sha256:141a9fb5df99...
342:    image: kong:3.6@sha256:a42d2b4503e7...
465:    image: otel/opentelemetry-collector-contrib:0.104.0@sha256:e07e325e303e...
484:    image: jaegertracing/all-in-one:1.56@sha256:d2cd4c226624...
562:    image: prom/prometheus:v2.51.0@sha256:5ccad477d005...
581:    image: gcr.io/cadvisor/cadvisor:v0.49.1@sha256:3cde6faf0791...
604:    image: grafana/grafana:10.3.3@sha256:8640e5038e83...

$ python3 -c "import yaml; d=yaml.safe_load(open('docker-compose.yml')); print('YAML OK')"
YAML OK

$ docker compose config --quiet && echo "compose-config OK"
compose-config OK
```

---

## Files changed

```
docker-compose.yml                                                              — 8 image refs pinned
team/remediation/2026-05-18-r4-pin-remaining-images/ISSUE_INTAKE.md            — created
team/remediation/2026-05-18-r4-pin-remaining-images/BASE_IMAGE_LOCK.md         — created
team/remediation/2026-05-18-r4-pin-remaining-images/99-report.md               — this file
```

---

## Deferred items

None. All 8 images from EV-GAP-006 are now pinned. The only remaining non-pinned `image:` entries are services with `build:` context (no separate `image:` line), which are intentional and out of scope.
