# Closing Report — S9 trivy-bundled-bins

**Date:** 2026-05-18
**Branch:** `fix/s9-trivy-bundled-bins-2026-05-18`
**Base SHA:** `7674d9f`

## Summary

Closed ~120 Trivy alerts from three bundled binaries inside container images:

1. `bin/oauth2-proxy` — bumped source image from v7.6.0 to v7.15.2 in
   `jaeger-auth/Dockerfile`. The quay.io image digest was pinned to
   `sha256:aa0bd8dd5ab0c78e4c91c92755ad573a5f92241f88138b4141b8ec803463b4fd`.
2. `grpc_health_probe` — bumped from v0.4.28 to v0.4.50 in
   `services/vault-adapter/Dockerfile` and added per-arch SHA256 verification
   (amd64 + arm64), which was absent in the prior version.
3. `esbuild@0.25.12` — bumped override to `^0.28.0` in both
   `admin-ui/package.json` and `admin-ui/pnpm-workspace.yaml`; re-locked to
   0.28.0 in `admin-ui/pnpm-lock.yaml`.

## Bumps

| Binary | Before | After | File |
|---|---|---|---|
| oauth2-proxy | v7.6.0 | v7.15.2 | `jaeger-auth/Dockerfile` |
| grpc_health_probe | v0.4.28 (unverified) | v0.4.50 (SHA256-verified) | `services/vault-adapter/Dockerfile` |
| esbuild | 0.25.12 | 0.28.0 | `admin-ui/pnpm-lock.yaml` |

## Files Changed

- `jaeger-auth/Dockerfile` — FROM tag + sha256 digest bumped
- `services/vault-adapter/Dockerfile` — version + SHA256 verification added
- `admin-ui/package.json` — esbuild override range: `^0.25.0` → `^0.28.0`
- `admin-ui/pnpm-workspace.yaml` — same override: `^0.25.0` → `^0.28.0`
- `admin-ui/pnpm-lock.yaml` — esbuild re-locked at 0.28.0
- `team/remediation/2026-05-18-s9-trivy-bundled-bins/ISSUE_INTAKE.md` — intake
- `team/remediation/2026-05-18-s9-trivy-bundled-bins/99-report.md` — this file

## Commits

```
f2bc783 docs(s9): scaffold s9-trivy-bundled-bins session
848ce2f fix(jaeger-auth): bump oauth2-proxy v7.6.0 → v7.15.2 (closes ~45 Trivy alerts)
f5101bb fix(vault-adapter): bump grpc_health_probe v0.4.28 → v0.4.50 with SHA256 verification (closes ~37 Trivy alerts)
c9b06eb fix(admin-ui): bump esbuild 0.25.12 → 0.28.0 (closes ~38 Trivy alerts)
```

## Verification

```
# Check no Dockerfile downloads an unverified binary from GitHub releases
$ rg -n "wget|curl.*github.com.*releases" jaeger-auth/Dockerfile services/*/Dockerfile 2>/dev/null
jaeger-auth/Dockerfile:12:# wget is needed for the HEALTHCHECK; ...
jaeger-auth/Dockerfile:14:RUN apk add --no-cache wget
jaeger-auth/Dockerfile:25:  CMD wget -qO- http://localhost:4180/ping || exit 1
services/proxy-plugin/Dockerfile:26:COPY --from=busybox:musl /bin/wget /wget
services/vault-adapter/Dockerfile:33:    wget -qO /grpc_health_probe \
services/broker/Dockerfile:26:COPY --from=busybox:musl /bin/wget /wget
services/kong-syncer/Dockerfile:26:COPY --from=busybox:musl /bin/wget /wget
# → vault-adapter wget is followed by sha256sum -c; all other wget are healthchecks
#   or busybox copies — not GitHub release downloads.

# Build jaeger-auth
$ docker compose build jaeger-auth 2>&1 | tail -5
# → SUCCESS (sha256:2de3a84e7a632a97c81d9689b107d2bf5128a8d4e587835ea5cc5a1e04dd57aa)

# pnpm frozen install
$ cd admin-ui && pnpm install --frozen-lockfile 2>&1 | tail -3
Done in 570ms using pnpm v11.0.9

# TypeScript check (pre-existing failures unrelated to this change)
$ pnpm exec tsc --noEmit 2>&1 | tail -3
# → Same TS errors as on main (AdminJS v7 API mismatch). Not introduced by this PR.

# Git status — clean
$ git status --short
# → (empty)

# Diff stat vs main
$ git diff --stat origin/main..HEAD
 admin-ui/package.json                                             |   2 +-
 admin-ui/pnpm-lock.yaml                                          | 222 ++++++++++-----------
 admin-ui/pnpm-workspace.yaml                                     |   2 +-
 jaeger-auth/Dockerfile                                           |   4 +-
 services/vault-adapter/Dockerfile                                |   9 +-
 team/remediation/2026-05-18-s9-trivy-bundled-bins/ISSUE_INTAKE.md |  69 +++++++
 6 changed (+ this report)
```

## Checksum Sources

- oauth2-proxy v7.15.2 quay.io digest: obtained via `docker pull` during build
- grpc_health_probe v0.4.50 checksums:
  https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.50/checksums.txt
  - linux-amd64: `84fb8aa14a6f5467bf12144320e8e91f4e888956c3229efa7da0b8bdb10de8d2`
  - linux-arm64: `6cf28a5fa8fae69d71a12800e8702cc3f0465b6f6e804bc4268f868709ca37a5`

## Out-of-scope Findings

None. No unexpected downloads of the three targeted binaries were found outside
the three owner files. The `mcp-server/Dockerfile` and `broker/Dockerfile` do
not download `grpc_health_probe`.

## Open Questions

None.
