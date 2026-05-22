# Issue Intake — S5: codeql-weak-hashing

**Session:** S5  
**Branch:** fix/s5-codeql-weak-hashing-2026-05-18  
**Date:** 2026-05-18  

---

## Problem statement

CodeQL `py/weak-sensitive-data-hashing` fires on three locations where
`hashlib.sha256` is used on sensitive data (API keys or audit-chain bytes).
All three currently use SHA-256 (not MD5/SHA-1). The rule fires because bare
SHA-256 on a credential lookup token — without HMAC or a per-secret salt —
is brute-forceable if an attacker obtains the stored fingerprint column.

## User-visible symptom

GitHub Security → Code scanning → 3 open HIGH alerts:

- `admin-api/src/admin_api/api/internal.py:119`
- `admin-api/src/admin_api/api/proxy.py:64`
- `mintkey-models/mintkey_models/audit.py:85`

## Expected behavior

All three alerts closed; codeql scan passes clean on this branch.

## Evidence

- `internal.py:119` — `fingerprint = hashlib.sha256(api_key.encode()).digest()[:8].hex()`
  Fingerprint is stored in `agents.api_key_fingerprint`; computed at key-creation
  time in `agents.py:_generate_agent_api_key()` (line 109, out of scope).
  Lookup query: `WHERE api_key_fingerprint = :fp`.

- `proxy.py:64` — `fingerprint = hashlib.sha256(api_key.encode()).digest()[:8].hex()`
  Fingerprint is stored in `service_api_keys.key_fingerprint`; computed at
  key-creation time in `api_keys.py:_fingerprint()` (line 107, out of scope).
  Lookup query: `WHERE sk.key_fingerprint = :fp`.

- `audit.py:85` — `return hashlib.sha256(canonical_bytes + prev_hash).digest()`
  Result stored as `audit_events.hash` / `audit_chain_state.head_hash`.
  Read back as `prev_hash` for each subsequent event.
  Also re-used by `audit-verify-job/verify.py:63` (identical SHA-256 call
  that verifies stored hashes; must stay in sync).

## Scope

Owner files:
- `admin-api/src/admin_api/api/internal.py`
- `admin-api/src/admin_api/api/proxy.py`
- `mintkey-models/mintkey_models/audit.py`
- Tests: `admin-api/tests/`, `mintkey-models/tests/`
- `team/remediation/2026-05-18-s5-codeql-weak-hashing/ISSUE_INTAKE.md` + `99-report.md`

## Out of scope

- `admin-api/src/admin_api/api/agents.py` — generates fingerprint at key-creation
- `admin-api/src/admin_api/api/api_keys.py` — generates fingerprint at key-creation
- `audit-verify-job/verify.py` — must stay in sync with audit.py
- DB migration scripts — not in this repo's Python source tree

## Risk level

`security / compliance`

## Classification — per-site analysis

### Site 1: `internal.py:119` — BLOCKED: migration needed

**Use:** DB lookup index (fingerprint-to-row pre-filter before Argon2id verify).  
**Old hash:** `hashlib.sha256`  
**Needed hash:** HMAC-SHA-256 with project-static lookup salt  
**Status:** BLOCKED

Reason: The fingerprint is stored in `agents.api_key_fingerprint` (column in DB).
The generating code is `agents.py:_generate_agent_api_key()` which is out of scope
for this session (owned by a different session). Changing the lookup hash algorithm
here without simultaneously updating the generator and migrating existing rows would
break authentication for all existing agents. This requires a coordinated migration:

1. Add `MINTKEY_FINGERPRINT_HMAC_KEY` env var (project-static secret)
2. Update `agents.py:_generate_agent_api_key()` to use `hmac.new(key, plaintext, sha256)`
3. Backfill-migrate existing `api_key_fingerprint` values in the DB
4. Update `internal.py:119` to use same HMAC

### Site 2: `proxy.py:64` — BLOCKED: migration needed

**Use:** DB lookup index (fingerprint-to-row pre-filter before Argon2id verify).  
**Old hash:** `hashlib.sha256`  
**Needed hash:** HMAC-SHA-256 with project-static lookup salt  
**Status:** BLOCKED

Same reason as Site 1. Generating code is `api_keys.py:_fingerprint()` (out of
scope). Changing this lookup without migrating `service_api_keys.key_fingerprint`
values would break authentication for all existing service API keys.

### Site 3: `audit.py:85` — BLOCKED: hash chain migration needed

**Use:** Audit hash chain integrity (collision resistance + tamper evidence).  
**Old hash:** `hashlib.sha256`  
**Correct hash per ADR-0014.7:** SHA-256 (documented as intentional)  
**Status:** BLOCKED / FALSE POSITIVE

This is the strongest case for pushing back on the CodeQL alert:
- SHA-256 is cryptographically appropriate for audit chain integrity (not a KDF use case)
- ADR-0014.7 explicitly mandates SHA-256 for this chain
- The goal is tamper evidence / collision resistance, not protection against brute-force
- Changing the algorithm requires: (a) a DB migration of all existing `hash`/`prev_hash`
  columns, (b) updating `audit-verify-job/verify.py:63` in lockstep,
  (c) resetting the chain head in `audit_chain_state` for each tenant

Recommended action: dismiss this alert in GitHub Security UI as a false positive
with justification "audit chain integrity hash — SHA-256 is mandated by ADR-0014.7;
this is not a password/credential hashing use case; migration risk outweighs benefit."

## Verification target

After migration (future session):
```bash
cd admin-api && python -m pytest tests/ -x -q
cd mintkey-models && python -m pytest tests/ -x -q
```
And: CodeQL scan on the branch shows 0 alerts for `py/weak-sensitive-data-hashing`.

## Owner decisions needed

1. **Site 1 & 2 migration:** Owner must decide whether to add a `MINTKEY_FINGERPRINT_HMAC_KEY`
   env var (project-static HMAC key) and schedule the fingerprint migration for all existing
   agents and service API keys. This is a breaking change requiring a maintenance window.

2. **Site 3 audit.py:** Owner must decide whether to:
   a. Dismiss the CodeQL alert as a false positive in GitHub Security UI (recommended), OR
   b. Schedule a full audit hash chain migration to BLAKE2b-256 (coordinated across
      `audit.py`, `audit-verify-job/verify.py`, DB schema, and all tenant chains)

## Risk level

security / compliance — all three changes blocked pending migration plan.
