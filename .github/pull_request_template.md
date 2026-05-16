# Pull Request

## Summary

<!-- What does this PR do, and why? One or two sentences. -->

## Linked issue / ADR

<!-- Link the GitHub issue and/or ADR(s) this PR satisfies.
     Example: Closes #42 | Satisfies ADR-0020, .kiro/specs/mintkey-mvp/requirements.md AC-12-3 -->

- Issue:
- ADR(s) touched:
- Spec AC(s) satisfied:

## Test plan

<!--
List the exact commands you ran and their expected output.
Verification-as-evidence is required — paste the actual output below in the
"Verification output" section.

Example:
  pytest tests/unit/admin_api/test_rotation.py -v    → N passed, exit 0
  pytest tests/architecture/ -q                      → 17 passed, exit 0
  make smoke                                         → E2E-01 passed, exit 0
-->

| Command | Expected result |
|---|---|
| | |

## Pre-submission checklist

- [ ] All hard rules from `CONTRIBUTING.md` followed (spec AC cited, ADR present if architectural, failing test before implementation, verification output included)
- [ ] `--no-verify` was NOT used on any commit in this branch
- [ ] No `Co-Authored-By: Claude` or other LLM-noreply trailers in any commit message
- [ ] Pre-alpha status has NOT been weakened (no new production-readiness claims)
- [ ] If touching architecture: an ADR has been created or referenced above
- [ ] Verification output is pasted below with commands and exit codes

## Verification output

<!--
Paste the actual stdout/stderr from the commands in your test plan.
Commands + exit codes are required. "Tests pass" without output is rejected.

Example:
  $ pytest tests/unit/admin_api/test_rotation.py -v
  ========== 14 passed in 0.43s ==========
  (exit 0)

  $ pytest tests/architecture/ -q
  ........17 passed in 1.2s
  (exit 0)
-->

```
# paste here
```
