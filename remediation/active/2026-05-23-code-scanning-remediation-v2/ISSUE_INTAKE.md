# Issue Intake — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`
**Owner:** architect (CiprianSpot)
**Triggered:** 2026-05-23
**Driver:** remediation-orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → fresh REVIEWERs Opus → final reviewer)
**Branch:** `fix/code-scanning-remediation-v2` (off `main @ 9559561` — post-PR-#90)

---

## Original brief (verbatim — user-provided, 2026-05-23)

> Please use the orchestrator pattern to fix the following issues. […]
> Current State (from latest scan): 68 alerts fixed, 332 remain open.
> Still Open — Your Target: 8 application-code alerts (see table in original brief).

## ORCHESTRATOR-corrected scope (after context-recon)

The 8 alerts split into TWO distinct populations:

### Genuine code fixes (3 alerts in scope of this PR)

| # | Alert | Rule | File:line | Why genuine |
|---|---|---|---|---|
| 1 | #1269 | `py/full-ssrf` | `apps/admin-api/src/admin_api/api/services.py:572` | Real SSRF. `httpx.AsyncClient.request(url=final_url, ...)` where `final_url` is built from operator-controlled inputs. Needs allowlist + private-IP block + scheme validation. |
| 2 | (subset of #1276/#1287 batch) | `py/clear-text-logging-sensitive-data` | `apps/seed-job/main.py:1075` | Real leak. `print(f"Bootstrap admin password: {password}")`. S6 closed the on-disk write but missed the stdout print. |
| 3 | #1260 | `PinnedDependenciesID` (Scorecard) | `.github/workflows/ci.yml:109` | Real unpinned. `run: pip install pyyaml` — no version, no hash. |

### False positives (5 alerts requiring SECURITY.md acceptance, NOT code change)

| # | Alert | Rule | File:line | Why FP |
|---|---|---|---|---|
| 4 | #1268 | `py/weak-sensitive-data-hashing` | `apps/admin-api/src/admin_api/api/proxy.py:64` | `hashlib.sha256(api_key.encode()).digest()[:8].hex()` is a *fingerprint for DB indexed lookup*. Full verification uses argon2 in `agents.api_key_hash` per ADR-0017.5. Replacing with argon2 would break the index pattern. |
| 5 | #1267 | `py/weak-sensitive-data-hashing` | `apps/admin-api/src/admin_api/api/internal.py:119` | Same fingerprint pattern as #1268 (the code comment literally says "same algorithm as agents.py _generate_agent_api_key"). |
| 6 | #1266 | `py/weak-sensitive-data-hashing` | `packages/python/mintkey-models/mintkey_models/audit.py:85` | Audit Merkle-chain hash per ADR-0014.7. Changing the algorithm breaks audit-chain integrity for every existing record. Already documented as ACCEPTED in `weak-hash-migration.md`. |
| 7 | #1261 | `py/clear-text-logging-sensitive-data` | `examples/python-agent-snippet/agent.py:90` | `jwt_preview` is already a 12-char prefix (`brokered_jwt[:12] + "..."`). The variable name signals intent. |
| 8 | #1288 | `PinnedDependenciesID` (Scorecard) | `apps/mock-backend/Dockerfile:15` | Dockerfile IS fully pinned (`FROM ...@sha256:` + `--require-hashes`). The 2nd `pip install --no-deps .` is intentional + documented (`--require-hashes` cannot apply to a local editable path). |

### Bulk taint-flow false-positives in seed-job (6 alerts; partial FP class)

`py/clear-text-logging-sensitive-data` fires on lines 396, 399, 412, 1025, 1031, 1077 of `apps/seed-job/main.py` because the function scope contains a variable named `password`. CodeQL's taint flow assumes any string-format print in that scope is potentially the password. Verified contents:

- 396: `print(f"Bootstrap: {_label} valid — skipping.")` — label only
- 399: `print(f"Bootstrap: {_label} INVALID (size={len(existing)}) — regenerating.")` — label + size
- 412: `print(f"Bootstrap: wrote {_label}")` — label only
- 1025: `print(f"Mirrored admin_password to host bind: {host_file}")` — file path only
- 1031: `print(f"WARN: could not mirror admin_password to {HOST_BOOTSTRAP_SECRETS_DIR}: {exc}")` — path + exception
- 1077: `print(f"Seed steps 1-5 complete. tenant={tenant_id} operator={operator_id}")` — UUIDs

None of these emit the plaintext password. Covered by C-4 SECURITY.md anchor (taint-flow scope FP pattern).

## Net plan

- **C-1 to C-3:** Three genuine fixes — atomic commits per file
- **C-4:** SECURITY.md addition documenting the 4 FP patterns + dismissal anchors. Operator applies the dismissals via GitHub UI using the anchor text after merge.
- **C-5:** Final fresh reviewer (full session audit)

## Constraints (carry from user's brief)

- Do NOT suppress/dismiss alerts in the GitHub UI from this session (operator does dismissals using anchors after merge)
- Do NOT commit secrets, API keys, or credentials
- Do NOT change application logic — only fix the security issues
- Do NOT add Co-Authored-By trailers (CLAUDE.md)
- One rule/family per commit
- All GitHub state-changes via Mintkey proxy
