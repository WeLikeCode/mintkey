# Dev Settings Backup & Recovery — Session Plan

**Session:** `2026-05-18-dev-settings-backup-recovery`
**Branch:** `fix/dev-settings-backup-recovery-2026-05-18` (from `main @ edc63bd`)
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Mission

Make sure no contributor (human or agent) ever again loses 10+ minutes of curated local dev state to a routine workflow. Land a safe backup command, a confirmation-gated restore command, guardrails on every destructive script, and documentation that surfaces the workflow before the first `docker compose down -v` is typed.

Every change traces to an `EvidenceRef` in `EVIDENCE_LEDGER.md`.

## Hard rules (carry over from prior sessions + this session's extras)

- **No destructive ops by me or any subagent** during this session — no `docker compose down -v`, no `git clean`, no `rm` on data dirs, no seed-reset.
- No `Co-Authored-By` trailer.
- No `--no-verify`.
- No edits to accepted ADRs.
- No edits to product code (`admin-api/`, `admin-ui/`, `mcp-server/`, `services/`, `mintkey-models/`, `mock-backend/`, `seed-job/`) **unless** an EvidenceRef proves it's the only way to close a critical destructive path AND owner has been escalated via `03-escalations.md`.
- Real secrets MUST NOT be committed. Backup scripts MUST default to redaction.
- Backups MUST land in a gitignored directory; the script verifies gitignore presence before write.
- Atomic commits — one chunk per commit.
- Validate via tools: `bash -n scripts/*.sh`, `shellcheck` if available, a dry-run smoke test of each new script.

## Chunks

| # | Wave | Owner | What | EvidenceRef anchors |
|---|---|---|---|---|
| C-1 | 0 | ORCHESTRATOR + Investigator subagent | Build `EVIDENCE_LEDGER.md` — inventory every at-risk setting + every destructive script | all categories A–K |
| C-2 | 1 | IMPLEMENTER (Sonnet) | `scripts/dev-backup.sh` + `scripts/dev-restore.sh` + `.mintkey-backups/` gitignore entry | EV-ENV-* + EV-VOL-* + EV-SECRETS-* |
| C-3 | 1 | IMPLEMENTER (Sonnet) | Guardrails: confirmation/dry-run/force on every destructive script identified by C-1 | EV-DESTRUCTIVE-* |
| C-4 | 1 | IMPLEMENTER (Sonnet) | Documentation — README dev section, `team/remediation/HOWTO-backup-before-reset.md`, troubleshooting docs | EV-DOC-* |
| C-5 | 2 | REVIEWER (Opus, fresh) | Audit: no secrets committed; every change has an EvidenceRef; dry-run + failure modes work; backup dir gitignored | all |

C-2, C-3, C-4 are parallelisable (disjoint file scope: scripts/ vs. scripts/*-existing vs. *.md).

## Sequencing

```
Wave 0:  [me + Investigator] → EVIDENCE_LEDGER + scaffold + commit
              │
              ▼
Wave 1:  [C-2 scripts] ∥ [C-3 guardrails] ∥ [C-4 docs]  (parallel)
              │
              ▼
Wave 2:  [C-5 fresh reviewer] → PASS_ALL gate
              │
              ▼
Wave 3:  push + PR via Mintkey proxy + admin-merge
```

## Closing acceptance criteria

- A developer runs `bash scripts/dev-backup.sh` before a reset and `bash scripts/dev-restore.sh --apply` after, and recovers their local state.
- `bash scripts/dev-backup.sh --dry-run` produces a manifest with no secret values in plaintext.
- `.mintkey-backups/` is gitignored.
- Every destructive script touched in C-3 requires `--force` (or interactive confirmation) and prints a 5-line warning of what will be destroyed.
- Every doc claim cites an EvidenceRef.
- Reviewer PASS_ALL on first pass (or strike-2 within 1 retry).
- PR opened + admin-merged via proxy.
- `99-report.md` includes literal verification command outputs + exit codes per the user's spec.
