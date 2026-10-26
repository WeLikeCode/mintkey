# Questions — audit-chain-verifiable

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | open | 1.1, 2.1, 2.2 | ambiguous | Postgres normalises JSONB numbers: a float written in exponent form with an integral value (for exa… |
| Q-002 | open | 1.1, 2.1, 2.2 | ambiguous | That stored rows round-trip `at` and the payload exactly is also shown by `tests/acceptance/test_au… |
| Q-003 | answered | 1.1, 2.1, 2.2 | ambiguous | `apps/audit-verify-job` has no deployment definition in this repository (no Dockerfile, compose ser… |
<!-- l4:index:end -->

---

## Q-001: Postgres normalises JSONB numbers: a float written in exponent form with an integral value (for exa…

- **Status:** open
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the reply was discarded: checked openspec/changes/audit-chain-verifiable/design.md:40 does not resolve
- **Blocking tasks:** 1.1, 2.1, 2.2
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
Postgres normalises JSONB numbers: a float written in exponent form with an integral value (for example `1e20`)
reads back as an integer and would not verify. Inferred from JSONB's numeric storage, not run here. The audit
payloads seen in the code carry ids, names, counts and flags; if a payload ever needs such floats, the writer
should hash the value Postgres returns (`SELECT CAST(:payload AS jsonb)`), a separate change.

Listed under "Open questions" in design.md.
Open-question-hash: 3ef0eeef2a4ddd9e

### Answer
<!-- write below this line -->
---

## Q-002: That stored rows round-trip `at` and the payload exactly is also shown by `tests/acceptance/test_au…

- **Status:** open
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the reply was discarded: checked spec:spec.md#requirement-one-canonical-form-for-the-audit-event-hash does not resolve
- **Blocking tasks:** 1.1, 2.1, 2.2
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
That stored rows round-trip `at` and the payload exactly is also shown by `tests/acceptance/test_audit_chain.py`
(`test_hash_computation_matches_spec`, Docker, run by ci.yml's acceptance job, not by the L4 gate); its CI status
was not checked here.

Listed under "Open questions" in design.md.
Open-question-hash: 510e3dd2c3a76943

### Answer
<!-- write below this line -->
---

## Q-003: `apps/audit-verify-job` has no deployment definition in this repository (no Dockerfile, compose ser…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1, 2.2
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
`apps/audit-verify-job` has no deployment definition in this repository (no Dockerfile, compose service or chart
job); who runs it and with which environment is not known.

Listed under "Open questions" in design.md.
Open-question-hash: 1e4ca768955a8d46

### Answer
<!-- write below this line -->
The repository confirms the observation and settles what it means for this unit. There is no Dockerfile, compose service or workflow step for apps/audit-verify-job (the Dockerfiles exist for every other app under apps/, the compose files and the GitHub workflows do not mention the job), and the project's MVP design, section 15, states how it is meant to run: a one-shot script scheduled by an external cron or Kubernetes CronJob, and in the compose deployment invoked ad hoc by an operator, with the on-demand verify-chain endpoint as the compose-time path. Its environment is the one main.py documents today, a DATABASE_URL with an asyncpg DSN, plus, after this change, mintkey_models importable, as design.md D6 and the proposal's Impact section prescribe (for example PYTHONPATH=packages/python/mintkey-models python apps/audit-verify-job/main.py). Nothing in tasks 1.1, 2.1 or 2.2 depends on a deployment definition: the tests write events through a fake session, put the three source directories on sys.path themselves, and load main.py with importlib, and the production code must not add a sys.path change. So proceed with the tasks as written and do not add a Dockerfile, compose service or chart job; that would be a deployment decision outside the proposal's scope. If a packaged deployment of the job is wanted later, it is a separate change for the architect.
