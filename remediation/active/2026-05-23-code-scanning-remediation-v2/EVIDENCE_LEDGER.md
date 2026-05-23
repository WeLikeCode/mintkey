# Evidence Ledger — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`
**Format:** per-finding row mapping each alert to its before/after state.

| EvidenceRef | Alert# | Rule | File:line | Before (pre-fix) | After (post-fix) | Verification |
|---|---|---|---|---|---|---|
| EV-FIX-1269 | #1269 | py/full-ssrf | apps/admin-api/src/admin_api/api/services.py:572 | `httpx.AsyncClient.request(url=final_url, ...)` with no allowlist | `_validate_test_url()` helper rejects private/loopback/link-local/multicast/reserved IPs + non-http(s) schemes; request only happens if validation passes | C-1 reviewer: curl against `http://127.0.0.1/` → 400 ssrf_rejected; curl against `https://api.github.com/` → 200 |
| EV-FIX-SEED-1075 | (subset of #1276/#1287) | py/clear-text-logging-sensitive-data | apps/seed-job/main.py:1075 | `print(f"Bootstrap admin password: {password}")` — plaintext to stdout | `print(f"Bootstrap admin password: written to bootstrap-secrets volume (fingerprint sha256:{...[:8]})")` | C-2 reviewer: cold-start + `docker compose logs seed-job \| grep -E "Bootstrap admin password:"` returns fingerprint line, no plaintext |
| EV-FIX-1260 | #1260 | PinnedDependenciesID | .github/workflows/ci.yml:109 | `run: pip install pyyaml` | `run: pip install pyyaml==6.0.2` (or current stable) | C-3 reviewer: YAML parse exit 0; "Validate Test Override" CI job passes on this branch |
| EV-FP-1268 | #1268 | py/weak-sensitive-data-hashing | apps/admin-api/src/admin_api/api/proxy.py:64 | SHA-256 truncated fingerprint for indexed DB lookup | SECURITY.md Pattern A documents; dismissal anchor provided | C-4 reviewer: SECURITY.md has Pattern A section with anchor text |
| EV-FP-1267 | #1267 | py/weak-sensitive-data-hashing | apps/admin-api/src/admin_api/api/internal.py:119 | Same as EV-FP-1268 | Same as EV-FP-1268 | Same |
| EV-FP-1266 | #1266 | py/weak-sensitive-data-hashing | packages/python/mintkey-models/mintkey_models/audit.py:85 | SHA-256 Merkle-chain audit hash per ADR-0014.7 | SECURITY.md Pattern B documents | C-4 reviewer: SECURITY.md has Pattern B section |
| EV-FP-1261 | #1261 | py/clear-text-logging-sensitive-data | examples/python-agent-snippet/agent.py:90 | `jwt_preview` already-redacted variable (`brokered_jwt[:12] + "..."`) | SECURITY.md Pattern C documents | C-4 reviewer: SECURITY.md has Pattern C section |
| EV-FP-1288 | #1288 | PinnedDependenciesID | apps/mock-backend/Dockerfile:15 | Dockerfile already fully pinned; local-package install can't `--require-hashes` | SECURITY.md Pattern E documents | C-4 reviewer: SECURITY.md has Pattern E section |
| EV-FP-SEED-396..1077 | (#1286, #1287 incl. 1075 fixed) | py/clear-text-logging-sensitive-data | apps/seed-job/main.py lines 396, 399, 412, 1025, 1031, 1077 | Taint-flow scope FP — function has `password` in scope but prints don't emit it | SECURITY.md Pattern D documents with per-line inventory | C-4 reviewer: SECURITY.md has Pattern D section with per-line inventory |

## Post-merge expected alert state

- Genuine fixes (3 alerts): after CodeQL re-scan (typically within 24h of merge), expect `state=fixed`
- FP anchors (5+ alerts): operator dismisses via GitHub UI using anchor text; `state=dismissed` with reason "won't fix" and the documented anchor comment

## Coverage check (post-implementation, C-5)

Every row above must have:
- A verification command run
- Captured exit code OR alert-state delta
- A SECURITY.md anchor (for FP rows) OR commit SHA (for genuine-fix rows)
