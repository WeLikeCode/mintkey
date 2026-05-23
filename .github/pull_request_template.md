# Pull Request

<!-- Mintkey PR template — every PR must complete every section below.
     Per F4 decision (2026-05-16-pattern-enforcement): even doc typos
     and dep bumps fill the Issue Definition (briefer is fine; empty is not).
     See remediation/README.md and CONTRIBUTING.md for the routing table. -->

## Change Type

- [ ] Remediation session
- [ ] Kiro/spec-driven feature
- [ ] Documentation-only
- [ ] Dependency-only
- [ ] Other

## Required Provenance

**For remediation:**

- Session folder: <!-- e.g. remediation/active/2026-05-16-oss-readiness/ -->
- Issue intake file: <!-- e.g. remediation/active/<session>/ISSUE_INTAKE.md -->
- Matrix row(s): <!-- e.g. R-4, R-5 -->
- Reviewer result: <!-- e.g. PASS_ALL 18/18 from REL-FINAL Opus review -->

**For Kiro/spec-driven work:**

- Requirement: <!-- e.g. .kiro/specs/mintkey-mvp/requirements.md AC-12-3 -->
- Design section: <!-- e.g. .kiro/specs/mintkey-mvp/design.md §3.4 -->
- Task: <!-- e.g. T-1.5.7 -->
- ADR/proposal, if applicable: <!-- e.g. ADR-0020 -->

## Issue Definition

**Required for every PR — even doc typos / dep bumps fill these (briefer is fine).**

- **Problem:** <!-- What is broken or risky? -->
- **Expected behavior:** <!-- What should happen instead? -->
- **Evidence:** <!-- Logs, screenshots, failing tests, commands, file:line refs -->
- **Scope:** <!-- Which areas were changed? -->
- **Out of scope:** <!-- Which areas were NOT touched? -->

## Verification

Paste command output and exit codes below. "Tests pass" without output is rejected.

- [ ] Tests run
- [ ] Linters/validators run
- [ ] Smoke/integration run if relevant
- [ ] Security/plaintext checks run if relevant

```
# paste actual command + stdout/stderr + exit codes here

```

## Agent/Automation Rules

If an LLM or automation helped on this PR, confirm:

- [ ] No `--no-verify` was used on any commit
- [ ] No unverified "tests pass" claim
- [ ] No unrelated refactor bundled with the fix
- [ ] No accepted ADR was edited (only corrigenda allowed on accepted ADRs)
- [ ] No `Co-Authored-By` trailer (LLM or otherwise) was added or required
