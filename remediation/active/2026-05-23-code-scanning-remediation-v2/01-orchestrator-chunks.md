# Chunk Catalog — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`
**Branch:** `fix/code-scanning-remediation-v2`

## Hard rules (every chunk)

- No accepted-ADR edits (`docs/architecture/01-architecture/adr/**` read-only)
- No `Co-Authored-By:` trailer (CLAUDE.md)
- No `--no-verify`
- Real secrets never written to repo
- One rule/family per commit
- `git mv` for any moves (none expected in this PR)
- DO NOT push (orchestrator handles push + PR open)

---

## C-1 — SSRF allowlist + private-IP block (alert #1269)

| Field | Value |
|---|---|
| Owner files | `apps/admin-api/src/admin_api/api/services.py` only |
| Rule | `py/full-ssrf` |
| Approach | Add a helper `_validate_test_url(url) -> tuple[bool, str|None]` that uses `urllib.parse.urlsplit` + `ipaddress` to: (a) require `http`/`https` scheme; (b) resolve hostname to IP; (c) reject if any resolved IP is in private/loopback/link-local/multicast/reserved range; (d) optionally allow operator-supplied env-var allowlist `MINTKEY_SSRF_ALLOWLIST`. Call the helper before `httpx.AsyncClient.request`. On rejection return 400 with `{"code": "mintkey:ssrf_rejected", "reason": <reason>, "host_redacted": <first 4 chars + ***>}`. |
| Verification | `pytest tests/acceptance/test_services_test_endpoint.py` (or equivalent) — should still pass; add a test case for the new ssrf-rejection path if a test file exists for this endpoint. `curl` against admin-api with a `127.0.0.1` URL → expect 400 ssrf_rejected; `curl` with `https://api.github.com` → expect 200 OK (proxied). |
| DoD | Single atomic commit `fix(admin-api): add URL allowlist + private-IP block to prevent SSRF in services.py (alert #1269)`. Update 02-matrix + 04-progress. |

## C-2 — seed-job plaintext password print (subset of #1276/#1287)

| Field | Value |
|---|---|
| Owner files | `apps/seed-job/main.py` only |
| Rule | `py/clear-text-logging-sensitive-data` (the SINGLE genuine instance at line 1075) |
| Approach | Replace `print(f"Bootstrap admin password: {password}")` with a fingerprint-only message: `print(f"Bootstrap admin password: written to bootstrap-secrets volume (fingerprint sha256:{hashlib.sha256(password.encode()).hexdigest()[:8]})")`. Add `import hashlib` if not already imported. |
| Forbidden | Do NOT touch lines 396, 399, 412, 1025, 1031, 1077 (covered by C-4 SECURITY.md anchor — these are taint-flow FPs). Verify them only; document in commit body. |
| Verification | Cold-start the stack (`docker compose down -v && docker compose up -d --wait`) then `docker compose logs seed-job 2>&1 \| grep "Bootstrap admin password:"` — should contain `fingerprint sha256:` but NOT the plaintext. `make admin-password` still returns the correct decrypted password. |
| DoD | Single atomic commit `fix(seed-job): redact plaintext bootstrap password from stdout (line 1075 — fingerprint only)`. |

## C-3 — ci.yml pip install pin (alert #1260)

| Field | Value |
|---|---|
| Owner files | `.github/workflows/ci.yml` only (and any docs/comments referring to that workflow's pyyaml pinning) |
| Rule | `PinnedDependenciesID` (Scorecard) |
| Approach | Line 109: change `run: pip install pyyaml` to `run: pip install pyyaml==6.0.2` (latest stable as of triage). Optionally `pip install --require-hashes -r <hash-file>` if other inline installs in this workflow already use the hash-file pattern — but if not, plain `==` pin matches the existing style for one-off installs. Audit the rest of the workflow for similar one-line `pip install <pkg>` (no version) patterns; pin any found in the same commit. |
| Verification | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` — exits 0. The workflow's "Validate Test Override" job should pass on PR CI. |
| DoD | Single atomic commit `fix(ci): pin pip install pyyaml in workflow (PinnedDependenciesID #1260)`. |

## C-4 — SECURITY.md FP-pattern documentation + dismissal anchors

| Field | Value |
|---|---|
| Owner files | `SECURITY.md` only |
| Rule | (doc-only; no code) |
| Approach | Add a new top-level section `## CodeQL + Scorecard — accepted false-positive patterns` after the existing "Accepted Scorecard Residuals" section. Document FOUR patterns: |

### Pattern A — SHA-256 truncated fingerprint for indexed DB lookup
- Sites: `apps/admin-api/src/admin_api/api/proxy.py:64`, `apps/admin-api/src/admin_api/api/internal.py:119` (and `apps/admin-api/src/admin_api/api/agents.py:_generate_agent_api_key` source of truth)
- Why: `hashlib.sha256(api_key.encode()).digest()[:8].hex()` produces a deterministic 64-bit fingerprint stored as an INDEXED column for O(log n) DB lookup. Full credential verification uses **argon2id** (`agents.api_key_hash`) per ADR-0017.5 — the SHA-256 fingerprint is NOT the security boundary.
- Why CodeQL is wrong: rule `py/weak-sensitive-data-hashing` heuristically flags any SHA-256/MD5/SHA-1 on a `*_key` variable. It doesn't model the two-tier (fingerprint-then-verify) pattern.
- Dismissal anchor: `False positive — see SECURITY.md §CodeQL accepted FP patterns / Pattern A (fingerprint for indexed lookup; argon2id is the security boundary).`

### Pattern B — SHA-256 Merkle-chain audit hash (ADR-0014.7)
- Sites: `packages/python/mintkey-models/mintkey_models/audit.py:85`
- Why: `hashlib.sha256(canonical_bytes + prev_hash).digest()` is the per-event Merkle-chain link. The hash is NOT used for confidentiality; it's used for integrity (tamper-evident audit log). SHA-256 is the appropriate cryptographic primitive per ADR-0014.7.
- Why CodeQL is wrong: rule flags SHA-256 on bytes that include event data (heuristic: "sensitive-looking" content). Misses that this is a tamper-evidence primitive, not a confidentiality primitive.
- Migration constraint: changing the algorithm breaks chain integrity for every existing audit record. Migration would require ADR + dual-hash transition window. Out of pre-alpha scope per `weak-hash-migration.md`.
- Dismissal anchor: `False positive — see SECURITY.md §CodeQL accepted FP patterns / Pattern B (Merkle-chain integrity hash per ADR-0014.7).`

### Pattern C — Already-redacted JWT preview variable
- Sites: `examples/python-agent-snippet/agent.py:90`
- Why: `jwt_preview` is constructed as `brokered_jwt[:12] + "..."` (12-char prefix + ellipsis). The variable name signals intent. The full JWT never leaves the variable `brokered_jwt`.
- Why CodeQL is wrong: rule taint-tracks any string containing `jwt`/`token`/`Bearer` to print/log sinks. Cannot model the upstream truncation.
- Dismissal anchor: `False positive — see SECURITY.md §CodeQL accepted FP patterns / Pattern C (already-redacted preview variable convention).`

### Pattern D — Taint-flow scope artifact in seed-job
- Sites: `apps/seed-job/main.py` lines 396, 399, 412, 1025, 1031, 1077
- Why: each `print()` in these locations emits a `_label`, file path, exception, or UUID — never the `password` variable that lives in the same function scope. The genuine plaintext leak (line 1075) is fixed by C-2 commit.
- Why CodeQL is wrong: taint-flow scope is function-level; any string-format expression in a function that has `password` in scope is conservatively flagged.
- Dismissal anchor: `False positive — see SECURITY.md §CodeQL accepted FP patterns / Pattern D (function-scope taint artifact; verified-no-leak inventory in the section).`

### Pattern E — Scorecard "PinnedDependenciesID" on Dockerfile editable-local install
- Sites: `apps/mock-backend/Dockerfile:15` (and the immediate `RUN pip install --no-deps .` line)
- Why: Dockerfile uses `FROM ...@sha256:` (image pinned) + `RUN pip install --require-hashes -r requirements-hashes.txt` (third-party deps pinned with hashes). The second `pip install --no-cache-dir --no-deps .` installs the local mock-backend package from `pyproject.toml`. `pip install --require-hashes` cannot apply to local-path installs (PEP 503 limitation); the workaround is documented in the Dockerfile comment.
- Why Scorecard is wrong: heuristic flags any `pip install` line without `--require-hashes`. Doesn't recognize the local-package exception.
- Dismissal anchor: `False positive — see SECURITY.md §CodeQL accepted FP patterns / Pattern E (Dockerfile local-package install; --require-hashes unavailable for local-path).`

| Verification | The new section parses as Markdown (renders cleanly). Anchor links resolve. No code change beyond the doc. |
| DoD | Single atomic commit `docs(security): add CodeQL + Scorecard accepted-FP-patterns section + dismissal anchors`. |

---

## C-5 — Final fresh REVIEWER (full-session audit, read-only)

Standard PR #90-style audit:
- Diff scope: every chunk's diff contained to its owner files
- Owner-files allowlist check
- No ADR edits
- No Co-Authored-By trailer
- Red-team grep: no real `mk_agent_*` / `mk_svckey_*` / `mk_agentkey_*` keys in diff
- Re-query GitHub for each addressed alert; confirm `state=open` STILL (because operator hasn't dismissed yet) but expect the alert's `most_recent_instance.commit_sha` to MATCH the new branch HEAD after CI re-scan (for genuine fixes). For SECURITY.md anchor: just confirm the doc section landed.
- `pytest tests/ --collect-only` exit 0
- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` exit 0
