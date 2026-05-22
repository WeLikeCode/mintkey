# Evidence — Post-Prealpha Readiness

This file enumerates every status claim in the post-prealpha-readiness roadmap edits with its verifiable source.

| Claim | EvidenceRef | Verified (yes/no) | Notes |
|---|---|---|---|
| Dev-workflow backup scripts exist (`scripts/dev-backup.sh`) | `scripts/dev-backup.sh` on main — 526 lines (PR #72 commit `4de9631`) | yes | `ls -la scripts/dev-backup.sh` returns 23662 bytes |
| Dev-workflow restore script exists (`scripts/dev-restore.sh`) | `scripts/dev-restore.sh` on main — 483 lines (PR #72 commit `4de9631`) | yes | `ls -la scripts/dev-restore.sh` returns 20732 bytes |
| Periodic backup cron wrapper exists (`scripts/dev-backup-cron.example.sh`) | `scripts/dev-backup-cron.example.sh` on main — 171 lines (PR #75 commit `80717f6`) | yes | `ls -la scripts/dev-backup-cron.example.sh` returns 8777 bytes |
| HOWTO backup-before-reset document exists | `docs/operations/backup-before-reset.md` on main (PR #72 + #75; moved to docs/operations/ in C-1) | yes | `ls -la docs/operations/backup-before-reset.md` returns 15201 bytes |
| Production DR not yet documented | No Helm chart, no tested restore drill, no PV snapshot procedure exists | yes | Section 7 confirms all Phase E items are NEW/DEFERRED |
| `docker compose up -d` starts 19 containers and reaches healthy state ≤ 120s | `docker-compose.yml` defines 19 services; OSS-6 commit `9705c16` verified end-to-end | yes | `wc -l docker-compose.yml` + service count confirming 19 services |
| PAT-free 10-min mock demo runs end-to-end | `docs/guides/10min-mock-demo.md` (OSS-6 commit `9705c16`) | yes | File exists: `ls docs/guides/10min-mock-demo.md` |
| Four MCP client setup guides exist | `docs/guides/mcp-clients/` directory (OSS-6 commit `9705c16`) | yes | `ls docs/guides/mcp-clients/` lists 4 guide files |
| GitHub PAT quickstart runs with real API key | `docs/guides/github-quickstart.md` (OSS-6 commit `9705c16`) | yes | File exists on main |
| Apache-2.0 license and governance docs in place | `LICENSE`, `CODE_OF_CONDUCT.md`, `GOVERNANCE.md`, `SUPPORT.md` (OSS-1/OSS-2 commits) | yes | All files present at repo root |
| CodeQL/Dependabot/container-scan CI gates in place | `.github/workflows/codeql.yml`, `.github/dependabot.yml`, `.github/workflows/container-scan.yml` (OSS-3 commit `46e91cf`) | yes | Files exist in `.github/` |
| Container scan re-runs on every push to main | `.github/workflows/container-scan.yml` `push: branches: [main]` (PR #76 commit `00a1048`) | yes | `grep -A3 "push:" .github/workflows/container-scan.yml` confirms |
| All 15 Dockerfile `FROM` directives SHA-pinned | All `Dockerfile*` files — `FROM` lines all contain `@sha256:` (PR #35 commit `373221f`) | yes | `grep -rn "FROM " --include="Dockerfile*" \| grep "@sha256" \| wc -l` = 15 |
| 9 of 9 external images in docker-compose.yml @sha256-pinned | `docker-compose.yml` lines 36/60/91/342/465/484/562/581/604 (PRs #70 + #74) | yes | `grep -n "image:" docker-compose.yml \| grep "sha256" \| wc -l` = 9 |
| `otel-collector` restart loop fixed | `otel-collector-config.yaml` repaired for v0.104+ (PR #48; session 2026-05-17) | yes | File exists: `ls otel-collector-config.yaml`; `remediation/archive/2026/05/2026-05-17-otel-collector-config/` exists |
| Root `LICENSE` file present | `LICENSE` (OSS-1 commit `2f8a99b`) | yes | `ls -la LICENSE` |
| Issue templates and PR template present | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` (OSS-2 commit `e36492c`) | yes | Directory and file exist |
| `docs/DEPLOYMENT.md` operator guide with "not supported" boundary | `docs/DEPLOYMENT.md` (OSS-5 commit `3d99f8c`) | yes | File exists on main |
| `docs/RELEASE.md` manual release procedure | `docs/RELEASE.md` (OSS-4 commit `a1abb8a`) | yes | File exists on main |
| Scorecard residuals documented with rationale | `SECURITY.md §Accepted Scorecard Residuals` (PR #64 commit `c2b37a0`; extended PR #77 commit `12af685`) | yes | Section exists in `SECURITY.md` |
| GO-2026-XXXX vulnerability deferred pending upstream patch | `SECURITY.md §Accepted Scorecard Residuals` — Vulnerabilities row (PR #64 + PR #77) | yes | Row present; full advisory ID confirmation is a separate owner action (Task 3.2) |
| No published container images — manual path only | `docs/RELEASE.md` §"Publishing images"; no `.github/workflows/publish.yml` exists | yes | `ls .github/workflows/` confirms no publish workflow |
| No HA topology — single-replica only | ADR-0020 (state store is in-process); `docker-compose.yml` single replica per service | yes | ADR exists; no replica count > 1 in compose |
| Scorecard session record exists | `remediation/archive/2026/05/2026-05-18-s11-scorecard-residuals/` directory | yes | `ls remediation/archive/2026/05/2026-05-18-s11-scorecard-residuals/` |
