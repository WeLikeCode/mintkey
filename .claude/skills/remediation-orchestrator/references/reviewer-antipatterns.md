# Reviewer anti-patterns checklist

Run each grep during every review. Paste the command and its output in the ANTI-PATTERNS section
of your reviewer report. Empty output is good. Non-empty output requires explanation.

---

## Faked / tautological tests

```bash
grep -rE 'assert True|assert 1 == 1|assert ""|expect\(true\)\.toBe\(true\)' tests/ spec/ e2e/ 2>/dev/null
```

```bash
# Python: assertion that can never fail
grep -rE 'assert\s+True\b|assert\s+1\s*==\s*1' tests/ 2>/dev/null
```

## Skip / xfail dodging

```bash
grep -rE 'pytest\.skip|@pytest\.mark\.xfail|test\.skip|test\.fixme|it\.skip|xit\(|xdescribe\(' tests/ spec/ e2e/ 2>/dev/null
```
Any hit without a `# TODO(<chunk-id>)` comment on the same line = FAIL.

## Mocking the system under test

Review the diff manually: is the code whose behavior the test is supposed to verify being
mocked away? A stub that always returns success without calling real logic = FAIL.

## Weakened assertions vs. the spec

Compare the new assertions against the relevant spec section. Did the assertion get
looser? For example: spec says "returns 201 with `key` field"; test only checks `status === 200` = FAIL.

## Commits made with --no-verify

```bash
git log --since={{session_start_date}} --format='%H %s' | head -20
# Then check each commit that landed in this session:
git show --stat <hash> | grep -i 'no.verify\|no.gpg'
```
Also check if any pre-commit hook files were modified:
```bash
git diff {{session_start_commit}}..HEAD -- .git/hooks/ .husky/ .pre-commit-config.yaml 2>/dev/null
```

## Canonical-doc edits (architecture / contract files)

```bash
git diff {{session_start_commit}}..HEAD -- docs/architecture/ specs/ openapi.yaml contracts/ 2>/dev/null | head -60
```
Any edit must be justified by the chunk's scope. If the contract was changed to match a
broken implementation (rather than fixing the implementation), = FAIL.

## Committed secrets

```bash
git diff {{session_start_commit}}..HEAD | grep -iE 'password\s*=|secret\s*=|api[_-]?key\s*=|token\s*=' \
  | grep -v 'placeholder\|example\|<.*>\|TODO\|#'
```

## Co-Authored-By Claude trailer

```bash
git log --since={{session_start_date}} --format='%B' | grep -i 'co.authored.by.*claude\|noreply@anthropic'
```
Any hit = FAIL (per project hard rules).

## URL-only / tautological integration test assertions

Review tests that make HTTP calls: does the assertion check only the status code, or does it
also verify meaningful response body content? Status-only = likely tautological. Require at
least one field-level assertion per endpoint under test.

## Tests that don't actually fail when the SUT is broken

The most important check: mentally (or by temporarily reverting the fix) ask "would this
test have failed before the fix was applied?" If the answer is no, the test is not guarding
the behavior it claims to guard = FAIL.
