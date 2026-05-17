# Issue Intake — 2026-05-18-s10-scorecard-pinned-deps

## Problem statement (required)

OpenSSF Scorecard raises 9 `PinnedDependenciesID` alerts against the Mintkey repository.
Two root causes: (1) at least one GitHub Actions `uses:` reference is pinned by floating
tag rather than by immutable 40-char commit SHA, allowing supply-chain tampering if the
upstream tag is moved; (2) `pip install` invocations in CI workflows and Dockerfiles do
not use `--require-hashes`, so package integrity is not verified at install time.

## User-visible symptom (required)

Scorecard pipeline reports score < 10 on the Pinned-Dependencies check. The SARIF upload
surfaces alerts in the GitHub Security tab for each unpinned reference.

## Expected behavior (required)

Every `uses:` line in `.github/workflows/*.yml` ends with a 40-hex-char SHA plus a
trailing `# <tag>` comment. Every `pip install` invocation that runs in CI either uses
`--require-hashes` with a hash-annotated requirements file, or is replaced by `uv` (which
the repo already uses for all Python services).

## Evidence (required)

- `.github/workflows/ci.yml:254` — `actions/upload-artifact@v4` (floating tag)
- `.github/workflows/ci.yml:73` — `pip install openapi-spec-validator jsonschema pyyaml` (no `--require-hashes`)
- `seed-job/Dockerfile:8` — `pip install --no-cache-dir -r requirements.txt` (no hashes)
- `mock-backend/Dockerfile:11` — `pip install --no-cache-dir -e .` (editable install, no hashes)
- `tools/deps.sh:87` — `uv pip install --system csvkit 2>/dev/null || pip3 install csvkit` (no hashes)

## Scope (required)

- `.github/workflows/*.yml`
- `seed-job/Dockerfile` and `seed-job/requirements.txt`
- `mock-backend/Dockerfile`
- `tools/deps.sh`
- New `seed-job/requirements-hashes.txt` if needed

## Out of scope (required)

Source code, ADRs, other Dockerfiles that don't use bare pip, Go modules, Node.js deps.

## Risk level (required)

`security` — supply-chain integrity; `CI` — affects CI score and badge.

## Verification target (required)

```bash
rg -nP "uses:\s+[\w-]+/[\w-]+@v?\d" .github/workflows/ | head -10   # must return 0 lines
rg -nP "uses:\s+\w+/\w+@[0-9a-f]{40}" .github/workflows/ | head -10 # shows SHA pins
rg -n "pip install" $(find services scripts admin-api mcp-server -name "*.sh" -o -name "Dockerfile" 2>/dev/null) | head -10
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in __import__('glob').glob('.github/workflows/*.yml')]" && echo "yaml-ok"
```

## Owner decisions needed (if any)

None — all SHAs cross-checked against existing pinned usages in the same repo.
