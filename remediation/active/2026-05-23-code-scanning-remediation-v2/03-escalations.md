# Escalations — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`

Open questions for owner. None active at C-0 time; populated as chunks run.

## Standing escalation triggers (any chunk → write here + STOP)

- **E-1:** An alert listed as "genuine fix" turns out to be a false positive on closer inspection (verify against ADRs first; promote to FP-anchor in C-4)
- **E-2:** Replacing the fingerprint pattern would actually be net-positive (e.g., argon2id verify is fast enough on this DB size, and dropping the fingerprint column simplifies the schema). Defer to architect; document tradeoffs.
- **E-3:** SSRF allowlist conflicts with operator workflow (operators legitimately need to test localhost/private-IP services for dev convenience). Decision: allow `MINTKEY_SSRF_ALLOW_PRIVATE=1` opt-in env var?
- **E-4:** ci.yml pip install pin breaks the workflow because the pinned version is too old/new for the script's actual import surface. Default: pin to current latest stable (`pyyaml==6.0.2`); if breakage, bump.
- **E-5:** Any new HIGH/CRITICAL alert introduced by a chunk's fix. Hard stop.

## Resolution log

(none yet)
