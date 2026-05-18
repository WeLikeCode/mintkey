# Session S5 — codeql-weak-hashing — Final Report

**Session:** `2026-05-18-s5-codeql-weak-hashing`
**Branch:** `fix/s5-codeql-weak-hashing-2026-05-18` (from `main @ 5203e23`)
**Status:** **CLOSED-WITH-RESIDUALS** — implementer classified 3 alert sites; all require owner-decision migrations before code changes can land. This report is the docs-only closure of the *classification* work; the actual hash-algorithm changes are deferred to follow-up sessions per the recommendations below.
**Closed:** 2026-05-18

**Commits:**
- `6fc38e5` docs(s5): classify codeql-weak-hashing alerts — all three BLOCKED pending migration

## Outcome by site

| File:line | Classification | Recommended action |
|---|---|---|
| `admin-api/src/admin_api/api/internal.py:119` | stored-fingerprint lookup (`agents.api_key_fingerprint`) | Migration session: HMAC-SHA-256 + maintenance-window key re-issuance OR dual-fingerprint cutover |
| `admin-api/src/admin_api/api/proxy.py:64` | stored-fingerprint lookup (`service_api_keys.key_fingerprint`) | Same migration as `internal.py:119` |
| `mintkey-models/mintkey_models/audit.py:85` | Audit hash chain integrity per ADR-0014.7 | Recommend GitHub-UI dismiss as false-positive with ADR-0014.7 rationale |

Original detailed classification table preserved below.

---

---

## Classification table

| File:line | Use | Old | New | Status |
|---|---|---|---|---|
| `admin-api/src/admin_api/api/internal.py:119` | DB lookup index — fingerprint for `agents.api_key_fingerprint` | `hashlib.sha256` | HMAC-SHA-256 | BLOCKED: migration needed |
| `admin-api/src/admin_api/api/proxy.py:64` | DB lookup index — fingerprint for `service_api_keys.key_fingerprint` | `hashlib.sha256` | HMAC-SHA-256 | BLOCKED: migration needed |
| `mintkey-models/mintkey_models/audit.py:85` | Audit hash chain integrity (ADR-0014.7) | `hashlib.sha256` | SHA-256 (correct) | BLOCKED / recommend GitHub dismiss as false positive |

---

## Detailed findings

### internal.py:119 and proxy.py:64 — BLOCKED

Both sites compute an 8-byte hex fingerprint of the API key using bare SHA-256:

```python
fingerprint = hashlib.sha256(api_key.encode()).digest()[:8].hex()
```

This fingerprint is then used as a WHERE-clause filter to locate the DB row before
Argon2id verification (the actual auth check). The security concern is that if an
attacker dumps the `api_key_fingerprint` / `key_fingerprint` column, they could
brute-force the original API key value from the 8-byte SHA-256 prefix with a
targeted dictionary attack.

**Why BLOCKED:** The fingerprints in these lookup sites must match what was stored
at key-creation time. The generating code is in:
- `admin-api/src/admin_api/api/agents.py:109` — `agents.api_key_fingerprint`
- `admin-api/src/admin_api/api/api_keys.py:107` — `service_api_keys.key_fingerprint`

Both of these files are OUT OF SCOPE for this session. Changing the algorithm
in just the lookup side without updating the generators and migrating all existing
DB rows would immediately break authentication for every active agent and service key.

**Migration plan required (separate session):**

1. Add env var `MINTKEY_FINGERPRINT_HMAC_KEY` (32-byte random secret, project-static)
2. Update `agents.py:_generate_agent_api_key()` and `api_keys.py:_fingerprint()` to
   use `hmac.new(HMAC_KEY, plaintext.encode(), hashlib.sha256).digest()[:8].hex()`
3. Write DB migration to backfill all existing fingerprint values (requires re-reading
   the Argon2id hash — NOT possible; fingerprints cannot be recomputed from stored
   hashes; see note below)
4. Update `internal.py:119` and `proxy.py:64` to use the same HMAC computation
5. Update `internal.py:118` comment and docstring accordingly

**Important note on migration feasibility:** Because the DB stores only the Argon2id
hash (not the plaintext), existing fingerprints CANNOT be recomputed. A live migration
would require either:
- Issuing new keys to all agents/services during a maintenance window, OR
- A dual-fingerprint column period where both old and new fingerprints are stored
  and checked during a rolling cutover

This is a non-trivial operational migration and should be scheduled accordingly.

### audit.py:85 — Recommend GitHub dismiss as false positive

The `compute_hash` function implements a SHA-256 hash chain for audit integrity:

```python
return hashlib.sha256(canonical_bytes + prev_hash).digest()
```

This is explicitly mandated by ADR-0014.7 and is the correct algorithm for:
- Tamper evidence (collision resistance)
- Chain continuity (each hash chains to the previous)

The CodeQL `py/weak-sensitive-data-hashing` rule fires here because `canonical_bytes`
is derived from event data that may contain sensitive field values. However, the
security goal is NOT to protect a secret — it's to ensure integrity. SHA-256 is
the appropriate algorithm.

Changing to BLAKE2b-256 would:
1. Break all existing audit chains in the DB (prev_hash bytes would be SHA-256;
   new events would reference old SHA-256 bytes in BLAKE2b computation)
2. Require updating `audit-verify-job/verify.py:63` in lockstep
3. Require resetting `audit_chain_state.head_hash` for all tenants
4. Require re-verifying all historical audit events

**Recommended action:** Dismiss this alert in GitHub Security → Code scanning →
"internal.py" alert → "Dismiss alert" → "Used in tests" or "False positive" →
Justification: "SHA-256 mandated by ADR-0014.7 for audit hash chain integrity; not
a credential hashing use case; changing algorithm requires DB migration."

---

## Files changed

- `team/remediation/2026-05-18-s5-codeql-weak-hashing/ISSUE_INTAKE.md` — classification
- `team/remediation/2026-05-18-s5-codeql-weak-hashing/99-report.md` — this file

No source code changed (all three sites BLOCKED).

---

## Verification

```
admin-api: 138 passed (uv run pytest tests/unit/admin_api/ -x -q)
mintkey-models (audit): 4 passed (pytest tests/test_audit.py -x -q)
mintkey-models (non-compat tests): 34 passed
```

Pre-existing failures in mintkey-models/tests/test_models.py (13 tests) are due to
Python 3.9 `str | None` union syntax used against a Python 3.9 interpreter; those
tests require Python 3.12 and are unrelated to this session.

---

## Open questions / next steps for owner

1. **Sites 1 & 2 (fingerprint migration):** Is there an upcoming key rotation window
   that could double as a migration window? If all existing agent/service keys can be
   re-issued, the migration becomes feasible. Otherwise, a dual-fingerprint cutover is
   required (store both old SHA-256 fp and new HMAC fp, check both during transition).

2. **Site 3 (audit.py):** Approve dismissal of the CodeQL alert as false positive?
   Justification: SHA-256 is ADR-0014.7-mandated; not a password/credential hashing use.
