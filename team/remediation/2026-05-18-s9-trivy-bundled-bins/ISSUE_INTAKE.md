# Issue Intake — s9-trivy-bundled-bins

## Problem statement

~120 open Trivy alerts originate from three bundled binaries that live inside
container images built from this repo. These are distinct from the base-image
CVEs closed in S2; they trace to specific binaries copied or downloaded at
image build time:

- `bin/oauth2-proxy` (45 alerts) — v7.6.0 of the oauth2-proxy binary is copied
  from `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` in `jaeger-auth/Dockerfile`.
- `grpc_health_probe` (37 alerts) — v0.4.28 of the probe is downloaded without
  SHA256 verification in `services/vault-adapter/Dockerfile`.
- `esbuild@0.25.12` (38 alerts, 19 in `node_modules/.pnpm/esbuild@0.25.12/…`
  + 19 in `@esbuild+linux-x64@0.25.12/…`) — locked at 0.25.12 in
  `admin-ui/pnpm-lock.yaml` via the `esbuild: ^0.25.0` override.

## User-visible symptom

GitHub Code Scanning / Trivy container-scan job reports ~120 CRITICAL/HIGH
findings linked to these three bundled binaries.

## Expected behavior

- `jaeger-auth` image ships oauth2-proxy v7.15.2 (latest patched release).
- `vault-adapter` image downloads grpc_health_probe v0.4.50 with verified
  SHA256.
- `admin-ui` lockfile resolves esbuild ≥ 0.28.0.
- CVE count drops by ~120 on re-scan.

## Evidence

- `jaeger-auth/Dockerfile:7` — `FROM quay.io/oauth2-proxy/oauth2-proxy:v7.6.0@sha256:dcb6ff8dd21bf3058f6a22c6fa385fa5b897a9cd3914c88a2cc2bb0a85f8065d`
- `services/vault-adapter/Dockerfile:26-29` — wget of v0.4.28, no checksum
- `admin-ui/pnpm-lock.yaml:12` — `esbuild: ^0.25.0` override pinned to 0.25.12

## Scope

- `jaeger-auth/Dockerfile`
- `services/vault-adapter/Dockerfile`
- `admin-ui/package.json` (override bump)
- `admin-ui/pnpm-lock.yaml` (re-lock after update)
- `team/remediation/2026-05-18-s9-trivy-bundled-bins/ISSUE_INTAKE.md`
- `team/remediation/2026-05-18-s9-trivy-bundled-bins/99-report.md`

## Out of scope

Any file not listed above. The other Dockerfiles (`broker/`, `proxy-plugin/`,
`kong-syncer/`, `mcp-server/`) do not download grpc_health_probe or
oauth2-proxy and are not touched.

## Risk level

`security` — CVE remediation. Low blast radius; only binary version pins
change.

## Verification target

```bash
rg -n "wget|curl.*github.com.*releases" --type-add 'docker:Dockerfile' --type docker
docker compose build jaeger-auth
cd admin-ui && pnpm install --frozen-lockfile && pnpm exec tsc --noEmit
```

## Owner decisions noted

- oauth2-proxy: bump FROM line tag + sha256 digest to v7.15.2.
- grpc_health_probe: bump to v0.4.50 and add sha256 verification.
- esbuild: bump override to `^0.28.0` and re-lock.
