# Mintkey Release Procedure (pre-alpha; manual)

> **Pre-alpha. Manual release only.** Mintkey does not currently publish
> container images automatically. This document describes the manual procedure
> a maintainer follows to cut a release of Mintkey for evaluation by self-hosters.
> Automated publishing to `ghcr.io/welikecode/mintkey-*` is deferred to a
> future session — see `remediation/archive/2026/05/2026-05-16-oss-readiness/03-escalations.md` E-5.

---

## Versioning policy

Mintkey is pre-alpha. Versions follow semver with explicit pre-release identifiers:

| Stage | Pattern | Notes |
|---|---|---|
| Current | `0.1.0-preview.N` | First OSS technical previews |
| Next | `0.1.0-alpha.N` | After preview phase, before semver stability |
| Later | `0.1.0-beta.N` | Feature-complete, hardening phase |
| Future | `0.1.0` | First stable; far from current |

The version source-of-truth spans five files that **must agree**. Any drift is
a P0 blocker for release.

| File | Field |
|---|---|
| `apps/admin-ui/package.json` | `version` |
| `packages/python/mintkey-models/pyproject.toml` | `[project] version` |
| `docs/architecture/contracts/rest/openapi.yaml` | `info.version` |
| `README.md` | status table wire-surface row |
| `CHANGELOG.md` | top entry header |

---

## Manual release procedure

### 1. Bump versions across all five files

Edit each file to the new version string (e.g. `0.1.0-preview.2`):

```bash
# apps/admin-ui/package.json  — "version" field
# packages/python/mintkey-models/pyproject.toml  — version = "..."
# docs/architecture/contracts/rest/openapi.yaml  — info.version: "..."
# README.md  — status table wire-surface row
# CHANGELOG.md  — top entry header (change UNRELEASED → today's date)
```

Verify alignment:

```bash
rg -n '0\.1\.0-preview\.' \
  README.md CHANGELOG.md \
  apps/admin-ui/package.json \
  packages/python/mintkey-models/pyproject.toml \
  docs/architecture/contracts/rest/openapi.yaml
```

Expect at least 5 hits (one per file).

Commit:

```bash
git add apps/admin-ui/package.json packages/python/mintkey-models/pyproject.toml \
  docs/architecture/contracts/rest/openapi.yaml \
  README.md CHANGELOG.md
git commit -m "chore: bump version to 0.1.0-preview.N"
```

### 2. Promote the CHANGELOG entry

In `CHANGELOG.md`, change the top entry from:

```
## [0.1.0-preview.N] — UNRELEASED — YYYY-MM-DD
```

to:

```
## [0.1.0-preview.N] — YYYY-MM-DD
```

Use today's actual release date.

### 3. Run the full verification gate

See [Verification gate](#verification-gate-run-before-tagging) below.
All commands must exit 0. If any fail, abort the release and fix first.

### 4. Tag the release

```bash
git tag v0.1.0-preview.N
```

Do not push the tag until images are built and verified locally (step 5).

### 5. Build images locally

```bash
docker compose build
```

Verify all images build without error. Record image digests:

```bash
docker images --filter "reference=mintkey-*" \
  --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}"
```

### 6. Push to GHCR — DEFERRED

Image publishing to `ghcr.io/welikecode/mintkey-*` is not automated yet.
See [GHCR image publishing](#ghcr-image-publishing--deferred) below.
Until the workflow exists, self-hosters build locally from the tagged commit.

### 7. Create a GitHub Release

Navigate to:

```
https://github.com/WeLikeCode/mintkey/releases/new?tag=v0.1.0-preview.N
```

- Set **Title**: `Mintkey v0.1.0-preview.N — Technical Preview`
- Paste the CHANGELOG entry for this version as the **release notes body**
- Prepend the standard pre-alpha disclaimer (see
  [Pre-alpha disclaimers](#pre-alpha-disclaimers-in-release-notes))
- Check **Set as pre-release**
- Do NOT check "Set as the latest release" until a stable release exists

### 8. Announce in GitHub Discussions

Post in the `Announcements` category:

- Link to the GitHub Release
- One-paragraph summary of what changed
- Reminder: evaluation use only, not for production, no support contract

---

## Verification gate (run before tagging)

All commands must exit 0. Capture output for the release notes.

```bash
make lint
make test-unit
make test-arch
make test-acceptance
docker compose build
docker compose up -d --wait --timeout 120
make smoke
docker compose down
```

Additional spot checks:

```bash
# Version alignment — expect ≥5 hits, no mismatches
rg -n '0\.1\.0-preview\.' \
  README.md CHANGELOG.md \
  apps/admin-ui/package.json \
  packages/python/mintkey-models/pyproject.toml \
  docs/architecture/contracts/rest/openapi.yaml

# Parse checks
python3 -c "import json; json.load(open('apps/admin-ui/package.json')); print('package.json OK')"
python3 -c "import yaml; yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')); print('openapi OK')"
python3 -c "import tomllib; tomllib.loads(open('packages/python/mintkey-models/pyproject.toml').read()); print('pyproject OK')"

# No old version strings left
rg '"version": "1\.0\.0"' apps/admin-ui/package.json && echo FAIL || echo OK
rg '^version = "0\.1\.0"$' packages/python/mintkey-models/pyproject.toml && echo FAIL || echo OK
rg '0\.1\.0-experimental' docs/architecture/contracts/rest/openapi.yaml && echo FAIL || echo OK

# No placeholder strings
rg '<repo-url>|<TBD-by-architect>|maintainers@example\.invalid' \
  README.md QUICKSTART.md SECURITY.md \
  docs/architecture/contracts/rest/openapi.yaml \
  marketing/index.html && echo FAIL || echo OK
```

---

## GHCR image publishing — DEFERRED

When the release workflow lands (future session), images will be published to:

| Image | Tag pattern |
|---|---|
| `ghcr.io/welikecode/mintkey-admin-api` | `0.1.0-preview.N`, `<sha7>`, `latest-preview` |
| `ghcr.io/welikecode/mintkey-mcp-server` | same |
| `ghcr.io/welikecode/mintkey-admin-ui` | same |
| `ghcr.io/welikecode/mintkey-broker` | same |
| `ghcr.io/welikecode/mintkey-vault-adapter` | same |
| `ghcr.io/welikecode/mintkey-proxy-plugin` | same |
| `ghcr.io/welikecode/mintkey-kong-syncer` | same |
| `ghcr.io/welikecode/mintkey-jaeger-auth` | same |

> Mock backend (`mintkey-mock-backend`) and seed job (`mintkey-seed-job`) are
> dev-only and will not be published to the public registry.

Each image will carry three tags:

- Full semver pre-release: `0.1.0-preview.N`
- Short commit SHA: `abc1234` (7 chars)
- Mutable channel tag: `latest-preview`

Until the workflow exists, self-hosters must clone the tagged commit and run
`docker compose build` locally. The images are not available on any public
registry.

---

## SBOM / provenance / signing — DEFERRED

The following supply-chain features are aspirational for the first formal alpha
release. Pre-alpha previews ship without them.

| Feature | Target release | Notes |
|---|---|---|
| SBOM (CycloneDX or SPDX) per image | 0.1.0-alpha.1 | via `syft` in release workflow |
| SLSA Build Level 3 provenance | 0.1.0-alpha.1 | GitHub Actions OIDC + `slsa-github-generator` |
| Image signing | 0.1.0-alpha.1 | `cosign` / sigstore keyless signing |
| Scorecard badge | 0.1.0-alpha.1 | `ossf/scorecard-action` |

Tracking: OSS-4 deferred list in
`remediation/archive/2026/05/2026-05-16-oss-readiness/03-escalations.md` (E-5).

---

## Pre-alpha disclaimers in release notes

Every GitHub Release body MUST include the following block verbatim at the top:

```markdown
> **Pre-alpha. Not for production use.** Mintkey is under active development.
> Breaking changes are expected between preview releases. There is no support
> contract; community help is best-effort via
> [GitHub Discussions](https://github.com/WeLikeCode/mintkey/discussions).
> See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the supported evaluation
> posture and explicit gaps.
```

---

## Rollback procedure

If a release is found to have a critical defect after tagging:

1. Delete the GitHub Release (do not delete the tag immediately — it anchors
   issue references).
2. Create a new patch tag: `v0.1.0-preview.N+1` with a fix commit.
3. Re-run the full verification gate.
4. Publish the new GitHub Release with a note referencing the retracted version.
5. In `CHANGELOG.md`, add a `### Retracted` note under the bad version entry
   explaining the reason.

Do not force-push tags to `main`. Retracted tags are preserved for traceability.
