# Base Image Lock — R-4 Pin Remaining Compose Images

**Session:** fix/r4-pin-remaining-images-2026-05-18
**Date:** 2026-05-18
**Closes:** EV-GAP-006 (DSBR ledger EV-COMPOSE-002 + EV-COMPOSE-003)
**Digest source:** `docker buildx imagetools inspect <image>:<tag>` — manifest list (top-level) digest

---

## Pin table

| Service | Old image (tag-only) | New image (tag + digest) | Source command |
|---|---|---|---|
| `keycloak` | `quay.io/keycloak/keycloak:24.0` | `quay.io/keycloak/keycloak:24.0@sha256:f8ade94c1d0ad2f2fa7734a455fee5392764f402c43ca35e9af6bf63a2541dc9` | `docker buildx imagetools inspect quay.io/keycloak/keycloak:24.0` |
| `liquibase` | `liquibase/liquibase:4.27.0` | `liquibase/liquibase:4.27.0@sha256:141a9fb5df99e43be49e507dc1892a65cd7b93c9e662c4212e834468df959983` | `docker buildx imagetools inspect liquibase/liquibase:4.27.0` |
| `kong` | `kong:3.6` | `kong:3.6@sha256:a42d2b4503e7b6674ca7914883bdb0d2274b806b0e397a6af28d1dd57aafce4e` | `docker buildx imagetools inspect kong:3.6` |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.104.0` | `otel/opentelemetry-collector-contrib:0.104.0@sha256:e07e325e303e86f4a87a617491e921b579a92da6d404007394757ac910bf9587` | `docker buildx imagetools inspect otel/opentelemetry-collector-contrib:0.104.0` |
| `jaeger` | `jaegertracing/all-in-one:1.56` | `jaegertracing/all-in-one:1.56@sha256:d2cd4c226624bdc116decd3106091b4df9882da8db42f8550293596cab79b8ea` | `docker buildx imagetools inspect jaegertracing/all-in-one:1.56` |
| `prometheus` | `prom/prometheus:v2.51.0` | `prom/prometheus:v2.51.0@sha256:5ccad477d0057e62a7cd1981ffcc43785ac10c5a35522dc207466ff7e7ec845f` | `docker buildx imagetools inspect prom/prometheus:v2.51.0` |
| `cadvisor` | `gcr.io/cadvisor/cadvisor:v0.49.1` | `gcr.io/cadvisor/cadvisor:v0.49.1@sha256:3cde6faf0791ebf7b41d6f8ae7145466fed712ea6f252c935294d2608b1af388` | `docker buildx imagetools inspect gcr.io/cadvisor/cadvisor:v0.49.1` |
| `grafana` | `grafana/grafana:10.3.3` | `grafana/grafana:10.3.3@sha256:8640e5038e83ca4554ed56b9d76375158bcd51580238c6f5d8adaf3f20dd5379` | `docker buildx imagetools inspect grafana/grafana:10.3.3` |

---

## Full digest index

| Image | Tag | sha256 manifest-list digest | Platforms |
|---|---|---|---|
| `quay.io/keycloak/keycloak` | `24.0` | `f8ade94c1d0ad2f2fa7734a455fee5392764f402c43ca35e9af6bf63a2541dc9` | linux/amd64, linux/arm64 |
| `docker.io/liquibase/liquibase` | `4.27.0` | `141a9fb5df99e43be49e507dc1892a65cd7b93c9e662c4212e834468df959983` | linux/amd64, linux/arm64 |
| `docker.io/library/kong` | `3.6` | `a42d2b4503e7b6674ca7914883bdb0d2274b806b0e397a6af28d1dd57aafce4e` | linux/amd64, linux/arm64, linux/arm/v7 |
| `docker.io/otel/opentelemetry-collector-contrib` | `0.104.0` | `e07e325e303e86f4a87a617491e921b579a92da6d404007394757ac910bf9587` | linux/386, linux/amd64, linux/arm64, linux/arm/v7 |
| `docker.io/jaegertracing/all-in-one` | `1.56` | `d2cd4c226624bdc116decd3106091b4df9882da8db42f8550293596cab79b8ea` | linux/amd64, linux/arm64, linux/s390x, linux/ppc64le |
| `docker.io/prom/prometheus` | `v2.51.0` | `5ccad477d0057e62a7cd1981ffcc43785ac10c5a35522dc207466ff7e7ec845f` | linux/amd64, linux/arm64/v8, linux/arm/v7, linux/ppc64le |
| `gcr.io/cadvisor/cadvisor` | `v0.49.1` | `3cde6faf0791ebf7b41d6f8ae7145466fed712ea6f252c935294d2608b1af388` | linux/amd64, linux/arm/v7, linux/arm64 |
| `docker.io/grafana/grafana` | `10.3.3` | `8640e5038e83ca4554ed56b9d76375158bcd51580238c6f5d8adaf3f20dd5379` | linux/amd64, linux/arm64, linux/arm/v7 |

---

## Already-pinned images (reference — postgres from PR #70)

| Service | Image | Digest | Pinned by |
|---|---|---|---|
| `postgres` | `postgres:16` | `b6ccf02e9b47eac0d67b5eaa0ef56fd59163bffa5506f64e96ceb5053130ec86` | PR #70 — 2026-05-18 dev-data wipe post-mortem |

---

## Notes

- All digests are **manifest list** (multi-arch index) digests, not platform-specific image digests. This matches the convention established by the existing `postgres:16` pin and is appropriate for `docker compose` which selects the platform-correct layer at pull time.
- Digests retrieved 2026-05-18 via `docker buildx imagetools inspect`. They should be refreshed whenever the corresponding tag is intentionally bumped to a newer upstream release.
- No tags were changed — only the `@sha256:` suffix was appended. Existing behavior (image version) is unchanged.
- `docker compose config --quiet` confirmed YAML parses cleanly with all 8 new pins applied.
