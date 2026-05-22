# Escalations — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`

Open questions for owner. Each is non-blocking for Phase 0 (C-0) — they need a decision before the chunk that depends on them commits.

---

## E-1 — Empty `internal/cfg/` and `internal/models/` disposition

**Question:** The directories `internal/cfg/` and `internal/models/` are empty on disk (no tracked files). They have 1-2 doc-only references in `.kiro/specs/mintkey-mvp/design.md` (an old/historical spec). The user's explicit move-list for Phase 3 names 7 packages (audit, auditq, changes, otelinit, svcid, ulid, vault) but does NOT mention cfg or models. Three options:

| Option | Action | Pros | Cons |
|---|---|---|---|
| E-1.A (default — chosen unless flagged) | Delete both empty dirs; leave the historical doc refs as-is (they describe state-at-mvp-spec-time) | Clean tree; honors user move-list exactly | Doc refs become dangling; reader has to know they're historical |
| E-1.B | Move both as empty placeholders to `packages/go/{cfg,models}/` | Keeps space for future packages | Adds clutter; no immediate semantic value |
| E-1.C | Delete + add a one-line note to the mvp spec saying "cfg/ and models/ packages planned in original MVP scope but not implemented; superseded by per-service config" | Cleaner doc; honors history | Touches a kiro spec that's historical |

**Default:** E-1.A. **Affected chunk:** C-3.

---

## E-2 — `tooling/` consolidation in or out of scope?

**Question:** The user's target tree shows `tooling/{scripts,ci,bootstrap,dev}/` but no phase in the brief explicitly assigns these moves. Currently at root: `tools/` (72 files-with-ref, 323 occurrences), `scripts/` (57/197), `bootstrap/` (12/35), `ci/` (7/9). Total: ~600 refs across ~150 files. Three options:

| Option | Action | Pros | Cons |
|---|---|---|---|
| E-2.A (default unless flagged) | OUT of scope this PR; follow-up `chore(repo): tooling/ consolidation` PR | Keeps this PR's blast radius manageable | Repo root keeps 4 top-level dirs that the user's target tree consolidates |
| E-2.B | Include in this PR as a 6th chunk (C-5.5 or expand C-4) | Single PR completes the layout | Doubles the path-ref update load; higher rollback cost |
| E-2.C | Move only `bootstrap/` + `ci/` (low-ref, low-risk); leave `tools/` + `scripts/` for follow-up | Compromise | Inconsistent intermediate state |

**Default:** E-2.A. **Affected chunk:** new chunk if owner picks B/C; otherwise none.

---

## E-3 — `realm-mintkey.json` location

**Question:** Per CD-2, the cleanest path is to leave `realm-mintkey.json` in `apps/seed-job/` because the seed-job Dockerfile `COPY realm-mintkey.json` from its build context. Moving it to `infra/keycloak/` requires widening the Docker build context (security regression) OR using buildkit's `--build-context` flag (Compose support is uneven). Two options:

| Option | Action | Pros | Cons |
|---|---|---|---|
| E-3.A (default) | Keep in `apps/seed-job/realm-mintkey.json`; document the rationale in 99-report | Zero risk to seed-job build | `infra/keycloak/` directory is empty / asymmetric vs other infra subdirs |
| E-3.B | Move to `infra/keycloak/realm-mintkey.json`; update seed-job Dockerfile to use `--build-context keycloak=../infra/keycloak` (buildkit) and update compose build context | Symmetric infra/ tree | Higher complexity; bound to specific Compose+buildkit version; potential CI break |

**Default:** E-3.A. **Affected chunk:** C-4. If E-3.B chosen: C-4 has 1 extra DoD (Dockerfile + compose changes).

---

## E-4 — Compose `include:` vs symlink for root shim

**Question:** Per CD-1, the root `docker-compose.yml` is a compatibility shim. Compose v2.20+ supports `include:`. Older versions need a symlink. Per `docker compose version` check at C-4 time, the implementer picks. Owner can override:

| Option | Action |
|---|---|
| E-4.A (default, if Compose ≥ 2.20) | Root `docker-compose.yml` with `include: - ./infra/compose/docker-compose.yml` (declarative, portable) |
| E-4.B | Root `docker-compose.yml` is a relative symlink to `infra/compose/docker-compose.yml` (universal but symlink may surprise Windows users) |

**Default:** E-4.A. **Affected chunk:** C-4.

---

## E-5 — `HOWTO-backup-before-reset.md` destination

**Question:** `team/remediation/HOWTO-backup-before-reset.md` (if present — to be confirmed by C-1 implementer reading the directory) is referenced from `docs/AUTH.md` and `docs/NETWORK.md` as an operator runbook. Two destinations:

| Option | Destination |
|---|---|
| E-5.A | `remediation/HOWTO-backup-before-reset.md` — keeps under remediation/, easy to find from session files |
| E-5.B (default) | `docs/operations/backup-before-reset.md` — promotes to canonical user docs since it's user-facing |

**Default:** E-5.B. **Affected chunk:** C-1.

---

## Owner sign-off

Until owner responds, implementers proceed with defaults (E-1.A, E-2.A, E-3.A, E-4.A, E-5.B). Each implementer SHALL note the assumed defaults in its commit message.
