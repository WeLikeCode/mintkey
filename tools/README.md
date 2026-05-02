# Tools

> Scripts the template ships for CI, audit, and bootstrap. None of them are language-specific.

## `bootstrap/` (separate top-level dir)

The wizard. Driven by `bootstrap/setup-wizard.sh`. See [`../BOOTSTRAP.md`](../BOOTSTRAP.md).

## `kiro-steering-audit`

Audit the steering set:

```bash
make audit-steering         # human-readable
make audit-steering JSON=1  # machine-readable JSON
```

Reports:
- Files in each inclusion mode (default / fileMatch / manual) with word counts
- `always` budget remaining (cap 5000 words)
- Files over the per-file word cap
- Files missing required frontmatter fields
- Files not reviewed in 90+ days (stale)
- Files with no triggers and no `manual`/`always` flag (dead)
- Duplicate content across files (fuzzy heading match)
- Cold files: declared `manual` or `fileMatch` but never hit in last 30 days

Exit codes:
- `0` — clean
- `1` — warnings
- `2` — errors (CI-blocking)

## `vibe-check`

Pre-PR script:

```bash
make vibe-check
```

Scans the staged diff for:
- New public functions / endpoints / events with no spec back-reference
- PR description missing `Spec:` / `ADR:` / `Contract:` citation
- Code files newer than the spec they claim to implement (timestamp inversion)

Default: warn locally, comment on PR, never block. Architect can promote individual checks to blocking.

## `spec-trace`

Generates a traceability matrix:

```bash
make spec-trace
```

Output: `.spec-trace/matrix.md` — every contract and ADR cross-referenced with the tests, code, and other docs that cite it. Reveals:
- ADRs with zero referencing tests (decoration risk)
- Tests with no spec back-reference (untraceable)
- Contracts with no fixtures or implementations

## `contract-lint`

Runs the contract toolchain:

```bash
make contract-lint
```

- spectral on `contracts/openapi/`
- asyncapi-cli on `contracts/asyncapi/`
- ajv on `contracts/jsonschema/` + `contracts/fixtures/`

Blocks CI on lint errors.

## `doctor`

Local environment health:

```bash
make doctor
```

Verifies:
- Wizard answers file is well-formed
- All conditionally-loaded steering files exist
- ADR template applied
- Architect-only CODEOWNERS in place
- Kiro / Claude Code can read the steering protocol
- Required language toolchains are installed and at the pinned version

Red items have a "How to fix" link.

## `template-diff`

Compare the engagement's files to the template version they were bootstrapped from:

```bash
make template-diff              # Show uncommitted changes to template-owned paths
make template-pull VERSION=0.2.0  # 3-way merge a new template version (requires 'template' remote)
```

See `.kiro/setup-state.json` for the template version this engagement was bootstrapped from.

---

## Adding a new tool

Tools should:
- Run on any CI provider (no GitLab-specific or GitHub-specific syntax)
- Run on any OS (or document the dependency)
- Have a `make <name>` target
- Have an exit-code contract documented in this file

If your tool is project-specific, it doesn't belong in the template — keep it in your engagement repo.
