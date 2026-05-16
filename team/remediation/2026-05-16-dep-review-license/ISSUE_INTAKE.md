# Issue Intake — 2026-05-16-dep-review-license

## Problem statement

The `dependency-review.yml` CI job fails on the `fix/python-test-infra-2026-05-16` PR because `pywin32@311` (a Windows-only transitive dependency pulled in by `testcontainers`) uses the `PSF-2.0` license (Python Software Foundation License 2.0), which is not in the `allow-licenses` list. PSF-2.0 is a permissive license compatible with Apache-2.0 and business-acceptable.

## User-visible symptom

```
The following dependencies have incompatible licenses:
admin-api/uv.lock » pywin32@311 – License: PSF-2.0
##[error]Dependency review detected incompatible licenses.
```

## Expected behavior

`dependency-review.yml` passes with `PSF-2.0` added to the allow-licenses list.

## Evidence

- CI run #25970209735, job #76340744174 on branch `fix/python-test-infra-2026-05-16`
- `pywin32@311` introduced by `testcontainers` (Windows IPC runtime dep)
- `.github/workflows/dependency-review.yml` `allow-licenses` does not include `PSF-2.0`

## Scope

`.github/workflows/dependency-review.yml` — add `PSF-2.0` to `allow-licenses`.

## Out of scope

All other workflow files; pyproject.toml; code; accepted ADRs. Must not add GPL-3.0, AGPL-3.0, or other strong-copyleft licenses.

## Risk level

CI (dependency-review gate).

## Verification target

```
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/dependency-review.yml'))"
# no exception — YAML valid
```
Full validation requires CI re-run on a PR with the updated workflow.

## Owner decisions needed

None. PSF-2.0 is clearly permissive and pre-approved by analogy with `Python-2.0` already in the list.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line or command)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (or "none")
