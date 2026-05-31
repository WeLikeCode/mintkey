# Hard rules — remediation-orchestrator

Every IMPLEMENTER and REVIEWER brief inherits these verbatim. They are non-negotiable.

- **Test-first.** When acceptance criteria say "tests added", write the failing test before the fix. Run it; watch it fail for the right reason; then write the minimum code that makes it pass.
- **Surgical changes only.** Every changed line must trace to a DoD item or a failing test. No drive-by refactors. No opportunistic cleanups. Match existing style.
- **Validate via tools — never claim done without running it.** Every claim of "done" must be backed by command output (curl, grep, pytest, screenshot Read, etc.). Subagent DoD = reproducible evidence; reviewers re-run each claim independently.
- **No `--no-verify` on commits or pushes.** Do not skip pre-commit hooks. Do not pass `--no-gpg-sign` unless the user explicitly requested it.
- **No `assert True` or tautological assertions.** No assertion that can pass without exercising the system under test.
- **No `pytest.skip` / `@pytest.mark.xfail` / `t.Skip` masking a real gap.** If you must mark something, attach a `# TODO(<chunk-id>)` comment explaining exactly which chunk will fix it.
- **No mocking the system under test.** You may mock external services; you may not mock the code whose behavior the test exists to verify.
- **No weakening assertions vs. the spec.** If the spec says X, the assertion must check X. Do not swap a precise assertion for a weaker one to make the test pass.
- **No edits to canonical docs to make a gate pass.** If a contract file (OpenAPI spec, ADR, architecture doc) is wrong or incomplete, STOP and open an open question. Do not change the contract to match a broken implementation; change the implementation to match the contract.
- **No destructive operations without explicit user authorization.** This includes: `docker compose down -v`, `git filter-repo`, `git push --force`, `git reset --hard`, `rm -rf`, dropping DB tables, killing processes. If a chunk requires one, ESCALATE.
- **No `Co-Authored-By: Claude` (or any `noreply@anthropic.com`) trailer on commit messages.** End the commit body without this trailer.
- **Conventional commits; one logical change per commit.** `feat(<scope>): ...` / `fix(<scope>): ...` / `test(<scope>): ...` / `docs(<scope>): ...`. No squashing across chunks.
- **For UI work: never mark a cell done without a real-browser screenshot you Read.** A passing test is necessary but not sufficient. Drive the browser; read the screenshot; describe what you saw.
- **Never push to a remote without explicit user authorization.** Commits stay local until the user says otherwise.
- **Preserve user data.** No destructive DB queries (DROP, TRUNCATE, DELETE without WHERE) without explicit user confirmation.
