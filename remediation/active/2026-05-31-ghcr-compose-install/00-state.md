# Remediation: compose-from-GHCR + curl-pipe install script + multi-arch images + skill bundling

**Session:** 2026-05-31-ghcr-compose-install
**Branch:** feat/ghcr-compose-and-install
**Pattern:** orchestrator (Sonnet implementer + fresh Opus reviewer, 3-strike hard-stop)

## Issue intake

- **Problem.** Operators currently have to clone the entire repo + build 10 images locally to run Mintkey. With GHCR publishing now in place (PR #130 merged, all 10 packages public), a clone-free install becomes possible.
- **Expected.** `curl -sSL <install.sh URL> | bash` (or downloaded-then-run) → working stack on any host with Docker, using prebuilt GHCR images. No repo clone required. Works on Intel x86_64 AND Apple Silicon (arm64) Macs natively.
- **Scope (in).** (a) `infra/compose/docker-compose.ghcr.yml` self-contained compose using `image: ghcr.io/welikecode/mintkey-<svc>:${MINTKEY_TAG:-latest}`. (b) `install.sh` that downloads compose + needed config files + generates KEK + runs `docker compose up -d`. (c) Brief docs/install snippet. (d) Multi-arch images via `publish.yml` (done in 79e1489). (e) Bundle the remediation-orchestrator skill in repo (done in 28959c3).
- **Scope (out).** Architectural rework to bake bind-mounted configs (kong.yml, liquibase changelog, prometheus.yml, grafana provisioning, jaeger config) into images. Install.sh will fetch them at install time. A future PR can move them into images.
- **Constraints.** No disruption to user's currently-running stack during validation. POSIX-compatible shell. Default visibility: PUBLIC GHCR (already verified). KEK generation handled by install.sh.
- **DoD.** (1) docker-compose.ghcr.yml passes `docker compose -f ... config` validation. (2) install.sh in a fresh temp dir successfully `pull`s all 10 images. (3) Compose `up` (in isolated --project-name) brings everything healthy. (4) Reviewer flip-tests: confirm install.sh works on a clean directory without the repo, and on multi-arch the right image manifest is pulled.

## Chunks

- **Chunk M (publish.yml multi-arch)** — DONE in 79e1489.
- **Chunk S (skill bundling)** — DONE in 28959c3.
- **Chunk I (compose-ghcr + install.sh)** — DISPATCHED to Sonnet implementer.

## Round history

- R1: dispatched Chunk I implementer (Sonnet).
- R2: Chunk I implementer completed. `infra/compose/docker-compose.ghcr.yml` + `install.sh` + `dev-install.sh` written; hardened KEK generation; multi-arch manifests (amd64 + arm64).

## Outcome — CLOSED 2026-05-31

Merged as PR #131 (`2d6763b`). `install.sh`, `dev-install.sh`, `infra/compose/docker-compose.ghcr.yml` on main. All DoD checks satisfied: compose config validates, install.sh pulls all images from GHCR, multi-arch manifests confirmed. Follow-up `9c9172c` hardened KEK + clarified README install paths.
