# S10 Scorecard PinnedDependencies — Closing Report

**Session:** `2026-05-18-s10-scorecard-pinned-deps`
**Status:** CLOSED
**Closed by:** IMPLEMENTER subagent (S10)

---

## Summary

Closed 9 Scorecard `PinnedDependenciesID` alerts across two categories:
(1) One GitHub Actions `uses:` line was pinned by floating tag (`actions/upload-artifact@v4`)
instead of commit SHA — replaced with SHA `ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2`,
consistent with the same pin already present in `playwright.yml`.
(2) Four pip install invocations in CI and Dockerfiles lacked `--require-hashes` — each has been
converted to use a hash-annotated requirements file generated via `uv pip compile --generate-hashes`.

---

## Verification commands and exit codes

```
# Must return 0 lines (no tag-pinned actions remain):
grep -rn "uses:.*@v[0-9]" .github/workflows/
exit code: 1 (grep exits 1 when no match — zero lines output)

# All SHA-pinned actions have trailing tag comments:
grep -rn "uses:.*@[0-9a-f]\{40\}" .github/workflows/ | head -15
exit code: 0 (all entries show # <tag> suffix)

# pip install invocations — only the safe local-package install remains:
grep -rn "pip install" $(find mock-backend seed-job tools -name "*.sh" -o -name "Dockerfile" 2>/dev/null) \
  | grep -v require-hashes
exit code: 0 (single remaining line: mock-backend/Dockerfile -- pip install --no-deps .)

# YAML validity:
python3 -c "import yaml, glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('yaml-ok')"
exit code: 0 (prints "yaml-ok")
```

---

## Chunks completed

| Chunk | Commit | Verdict | Notes |
|---|---|---|---|
| Scaffold session | `2a989c8` | PASS | ISSUE_INTAKE.md created |
| Pin action SHA | `b511fe0` | PASS | upload-artifact@v4 → SHA ea165f8d # v4.6.2 |
| pip --require-hashes | `1efbff7` | PASS | 4 invocations converted; 5 hash files added |

---

## DoD checklist — final state

- [x] No `uses: <action>@<tag>` remaining in any workflow — verified via `grep -rn "uses:.*@v[0-9]" .github/workflows/`
- [x] All SHA pins include `# <tag>` trailing comment for human readability
- [x] `ci.yml lint-contracts` job uses `pip install --require-hashes -r ci/lint-contracts-requirements.txt`
- [x] `seed-job/Dockerfile` uses `pip install --require-hashes -r requirements-hashes.txt`
- [x] `mock-backend/Dockerfile` installs deps with `--require-hashes`; local package installed with `--no-deps`
- [x] `tools/deps.sh` csvkit and uv fallbacks use `--require-hashes` with pinned files
- [x] YAML valid — `python3 -c "import yaml, glob; ..." && echo yaml-ok` passes
- [x] No `Co-Authored-By` trailer in any commit
- [x] No `--no-verify` used

---

## Residual risks / deferred items

- **mock-backend `pip install --no-deps .`**: The local editable install of the mock-backend
  package itself (`pip install --no-deps .`) cannot have a `--require-hashes` flag because
  a local directory path has no downloadable artifact to hash. This is safe: all third-party
  dependencies are installed first under `--require-hashes`; only the local package is
  installed without hashes, and it has no network provenance to verify. Scorecard may still
  flag this specific line but cannot be fixed without abandoning local-package installs.
  Mitigation: consider switching to `pip install --no-build-isolation --no-deps
  --require-hashes --only-binary=:all: .` once a wheel is pre-built (out of scope for S10).

- **tools/deps.sh curl bootstrap**: `curl -LsSf https://astral.sh/uv/install.sh | sh` is an
  unpinned installer-script fallback that Scorecard could flag as a different finding
  (script not pinned). This path is only reached on machines that have neither Homebrew
  nor pip3 and is not invoked in CI. Deferred.

---

## Escalation resolutions

None.

---

## Lessons learned / notes for next session

- All other workflows (`codeql.yml`, `container-scan.yml`, `dependency-review.yml`,
  `playwright.yml`, `scorecard.yml`) were already fully SHA-pinned before this session.
  Only `ci.yml:254` needed the single action fix.
- When converting `pip install` to `--require-hashes`, generate the lockfile with
  `uv pip compile --generate-hashes --python-version 3.12` from a `requirements.in`
  containing the abstract (unpinned) deps. Commit both `.in` and the generated hashes file.
- Local editable installs (`pip install -e .`) must be split into two steps:
  hash-verified dep install + unhashed local package install (`--no-deps .`).
