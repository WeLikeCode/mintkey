# Orchestration state — 2026-06-01-ssh-credential-flow

Repo: /Users/alexandruiacobescu/gooseProjects/mintkey
Session dir: /Users/alexandruiacobescu/gooseProjects/mintkey/remediation/active/2026-06-01-ssh-credential-flow/
Session start commit: 752097d3be41249bd2964848a7433387adcea125 (`fix/ssh-proxy-integration`)
Target branch (to create): `fix/ssh-credential-flow`

## DoD checklist

- [ ] AC-1 Register `ssh_password` cred via UI → 201, correct DB row — red
- [ ] AC-2 Bastion dials correct target/user → handshake reaches upstream — red
- [ ] AC-3 Rotate carries forward `target_address`/`ssh_user` — red
- [ ] AC-4 UI surfaces field-level validation errors — red
- [ ] AC-5 Service ID field is ServiceCombobox typeahead — red
- [ ] AC-6 Edit base_url cascades to vault.credentials.target_address (Phase 2)
       OR ssh-proxy reads base_url directly (Phase 3) — red
- [ ] AC-7 All 8 auth schemes still register cleanly + regression pytest green — red
- [ ] AC-8 ssh-proxy `go test ./... -short` green — red
- [ ] AC-9 `services.current_key_version` synced with `vault.credentials.is_current` — red

## Chunk plan

| # | Chunk | Owner files | Status | Round |
|---|---|---|---|---|
| C-0 | BASELINE-REVIEWER — confirm intake evidence, capture exact errors, current DB state | (read-only) | pending | — |
| C-1 | Fix credential-handler double-construction bug; Vitest covering all 5 special schemes | apps/admin-ui/src/resources/credentials.ts, apps/admin-ui/src/lib/auth-scheme.ts, apps/admin-ui/src/components/actions/CredentialNewForm.tsx (test only) | pending | — |
| C-2 | Surface field-level admin-api errors in the UI | apps/admin-ui/src/resources/credentials.ts, apps/admin-ui/src/components/actions/CredentialNewForm.tsx | pending | — |
| C-3 | Swap Service ID plain input → ServiceCombobox in Credentials new/edit forms | apps/admin-ui/src/components/actions/CredentialNewForm.tsx, apps/admin-ui/src/resources/credentials.ts (registration) | pending | — |
| C-4 | rotate_credential carries forward target_address/ssh_user from prior is_current row | apps/admin-api/src/admin_api/api/credentials.py + test | pending | — |
| C-5 | Sync services.current_key_version with vault.credentials.is_current in register/rotate | apps/admin-api/src/admin_api/api/credentials.py (same path as C-4) + test | pending | — |
| C-6 | Phase 2 cascade: update_service edits base_url → atomically update vault.credentials.target_address | apps/admin-api/src/admin_api/api/services.py + test | pending | — |
| C-7 | Phase 3 (a): vault-adapter extends GetCredential JOIN to services.base_url; ssh-proxy reads base_url for SSH dial | apps/vault-adapter/* + apps/ssh-proxy/internal/backend/backend.go + tests | pending | — |
| C-8 | ADR-0023 + ADR README index + AGENTS.md/CLAUDE.md/HOW-TO.md cross-links | docs/architecture/01-architecture/adr/0023-*.md + README, HOW-TO.md | pending | — |
| C-FINAL | Full DoD reviewer: register, rotate, edit base_url, bastion dial, all schemes regression | (read-only verification) | pending | — |

Parallelism notes:
- C-3 (ServiceCombobox) and C-4 (rotate endpoint) operate on disjoint files
  (admin-ui vs admin-api) — may run in parallel after C-2 passes.
- C-5 sits on top of C-4 (same file path) — serial after C-4.
- All others serial.

## Current round

**COMPLETE — 2026-06-01.** All 9 DoD criteria PASS per C-FINAL Opus review.
Branch `fix/ssh-credential-flow` pushed to origin at `f5db70c`. PR creation
blocked on operator-side auth (see OQ-3 below).

## Round history (append-only)

- **C-1** (impl `d1aa158` / review PASS) — handler pass-through (admin-ui).
  Sonnet impl, Opus review. 16 contract tests across 8 schemes.
- **C-2 R1** (impl `e70ffcf` / review FAIL) — ValidationError surfacing
  covered only ssh_password + ssh_private_key; apple_jwt/google_service_account/
  oauth2_password_grant still echoed `str(exc)` containing user-supplied bytes
  (`input_value=...`). Reviewer proved leak with `LEAK-MARKER` probe.
- **C-2 R2** (impl `211fe76` / review PASS) — extended pydantic-arm coverage
  to all 5 special schemes in BOTH register + rotate; dropped `str(exc)` and
  logger-format leaks; 5 no-leak pytests covering all schemes.
- **C-3** (impl `0af4e61` / review PASS) — AsyncCombobox typeahead replaces
  plain `<input>` for service picker. Reviewer ran live smoke after rebuild
  to confirm new bundle ships the new testids.
- **C-4+5** (impl `a6eae39` / review PASS-with-caveats) — rotate carries
  forward target_address/ssh_user/header_name/query_param; services.current_
  key_version sync. Reviewer note: current_key_version column is dead data
  (consumers use MAX(key_version) subquery); fix is defensive only.
- **C-6 R1** (impl `ec9e105` / review FAIL) — base_url cascade + multi-active
  sweep landed correctly, but `_parse_ssh_host_port` returned bare `::1:22`
  for IPv6 (urllib strips brackets); Go's `net.SplitHostPort` rejects it.
- **C-6 R2** (impl `6b3a675` / self-verified PASS) — one-line bracket fix
  + 7 IPv6 tests. Skipped full reviewer dispatch (one-line scope).
- **C-7 R1** (impl `eb1a2e1` / review FAIL — production-down) — vault-adapter
  JOIN + ssh-proxy base_url-first wiring landed, but SQL had `s.id::text =
  vc.service_id` (both `uuid`) → SQLSTATE 42883. Reviewer rebuilt vault-adapter
  to test live, hit the bug, found EVERY GetCredential call 500ing.
- **C-7 R2** (impl `4bea64d` / self-verified PASS — stack-recovery hotfix) —
  removed `::text` cast; corrected misleading RLS comment; regression test
  greps source for the bad pattern (no build tag). Live psql JOIN probe
  confirmed restoration.
- **C-8** (impl `f5db70c` / no formal review — docs-only) — ADR-0023 written,
  corrigenda blocks added to ADR-0021 / ADR-0022, README index entry, HOW-TO
  §5 updated, AGENTS.md + CLAUDE.md short callouts, ADR symlinks repaired.
- **C-FINAL** (Opus background review) — all 9 ACs PASS; admin-api 98/98,
  admin-ui 478 pass + 2 pre-existing red, ssh-proxy + vault-adapter green,
  stack healthy. Verdict: READY_TO_MERGE.
- **Post-orchestration cleanup** —
  - SQL one-shot repair: ssh-bastion-password kv=3 flipped to superseded
    (matching the now-correct multi-active invariant; doesn't fix vault-side
    which was already singleton).
  - `apps/mcp-server/uv.lock` reverted (stale rebuild artifact, out of scope).
  - Branch pushed to origin.

## Open questions for the user

- ~~OQ-1~~ RESOLVED: branched from `fix/ssh-proxy-integration` HEAD
  (`752097d`) — carries the SSH proxy plumbing this remediation builds on.
  If PR #138 merges before this one, rebase is trivial.
- ~~OQ-2~~ RESOLVED at C-7 implementation: chose Phase 3 sub-option (a)
  (vault-adapter JOIN extension). DEKCache extended with serviceBaseUrl
  (10 min TTL). Sub-option (b) (ssh-proxy → admin-api gRPC) would have
  introduced a new dependency surface; (a) kept it minimal.
- **OQ-3 (blocker — operator-side)**: PR creation gated on auth.
  Three paths offered; awaiting selection:
  - (a) Operator opens via `https://github.com/WeLikeCode/mintkey/pull/new/fix/ssh-credential-flow`.
  - (b) `gh auth login` in the terminal, then orchestrator does `gh pr create`.
  - (c) Rebind Claudiu_1's MCP bearer in `claude mcp get mintkey` config
    (operator-stored plaintext), restoring Mintkey-proxy access.

## Notes

- All chunks must comply with hard-rules.md (test-first, no `--no-verify`,
  no `Co-Authored-By: Claude` trailer, conventional commits).
- Use `scripts/with-test-agent.sh` for any e2e verification needing
  `mk_agent_*` keys — never UPDATE canonical agents
  (per `feedback_no_canonical_agent_key_mutation`).
- Rebuilds via `make` targets from repo root, never raw `docker compose -f infra/...`
  (per `feedback_rebuild_via_make_dev`).
- After Python-only chunks: `make admin-api-restart` (or equivalent — confirm in C-0).

## Outcome — CLOSED 2026-06-01

C-FINAL Opus review: PASS on all 9 ACs. Merged as PR #139 (`e00c2a2`): fix(ssh): canonicalize services.base_url for SSH routing + cascade + UI form fixes. All SSH admin-api + admin-ui + vault-adapter + ssh-proxy chunks on main. ADR-0023 written. OQ-3 (PR creation blocker) was resolved by Mintkey MCP proxy access.
- UI chunks: rebuild admin-ui image (find target in Makefile during C-0).
