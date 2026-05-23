# Dependency Review License — Closing Report

**Session:** `2026-05-16-dep-review-license`
**Status:** CLOSED
**Closed by:** super-orchestrator (2026-05-16)

---

## Summary

Added `PSF-2.0` to the `allow-licenses` list in `.github/workflows/dependency-review.yml`. The PSF-2.0 (Python Software Foundation License 2.0) was rejected for `pywin32@311`, a Windows-only transitive dependency introduced by `testcontainers` (via Session 3). PSF-2.0 is a permissive license compatible with Apache-2.0 — analogous to `Python-2.0` which was already in the list. YAML validated successfully.

---

## Verification commands and exit codes

```
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/dependency-review.yml'))"
exit code: 0  (no exception — YAML valid)
```

Full CI validation: the `dependency-review.yml` job will re-run on this PR and should pass.

---

## Chunks completed

| Chunk | Commit | Reviewer verdict | Rounds |
|---|---|---|---|
| C-1: Add PSF-2.0 to allow-licenses | (see git log) | PASS | 1 |

---

## DoD checklist — final state

- [x] PSF-2.0 added to allow-licenses — verified via YAML parse (exit 0)
- [x] No strong-copyleft license added
- [x] YAML valid — `python3 -c "import yaml; yaml.safe_load(...)"` exits 0
- [x] No `Co-Authored-By` trailer in any new commit
- [x] No `--no-verify` used

---

## Residual risks / deferred items

None. `requests@2.34.2` and `testcontainers@4.14.2` show as "license undetected" (not incompatible) — these don't cause CI failure per the dependency-review-action behavior (only incompatible causes failure, not undetected).

---

## Escalation resolutions

None.

---

## Licenses added and rationale

| License | Package | Rationale |
|---|---|---|
| PSF-2.0 | pywin32@311 | Python Software Foundation License 2.0 — permissive, compatible with Apache-2.0; analogous to Python-2.0 already in list |
