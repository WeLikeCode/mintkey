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
| Q-001 | answered | 1.1, 2.1, 2.2 | ambiguous | Postgres normalises JSONB numbers: a float written in exponent form with an integral value (for exa… |
| Q-002 | answered | 1.1, 2.1, 2.2 | ambiguous | That stored rows round-trip `at` and the payload exactly is also shown by `tests/acceptance/test_au… |
| Q-003 | answered | 1.1, 2.1, 2.2 | ambiguous | `apps/audit-verify-job` has no deployment definition in this repository (no Dockerfile, compose ser… |
| Q-004 | answered | 2.2 | technical | tests/unit/admin_api/test_audit_verify_endpoint.py:49-91 still hashes rows with the old three-field form |
<!-- l4:index:end -->

---

## Q-001: Postgres normalises JSONB numbers: a float written in exponent form with an integral value (for exa…

- **Status:** answered
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
None that block. The audit payloads this unit hashes carry ids, names, counts and flags, never floats in exponent form, so JSONB's number normalisation does not change any hash it verifies. If a payload ever needs such floats, the writer should hash the value Postgres returns; that is a separate change, as design.md's open questions say. Implement the tasks as written. (Answered by the owner's delegate.)
---

## Q-002: That stored rows round-trip `at` and the payload exactly is also shown by `tests/acceptance/test_au…

- **Status:** answered
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
None that block. proposal.md (Impact, stored events) settles it: the canonical form is the one every stored hash was computed with and compute_hash's result does not change, so tests/acceptance/test_audit_chain.py keeps passing. That Docker test runs in the repository's CI (ci.yml, on pull requests into main), not in the L4 gate; its result is a person's check when staging is promoted. This unit's acceptance is its unit tests, including the golden digest. Implement the tasks as written. (Answered by the owner's delegate.)
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

---

## Q-004: tests/unit/admin_api/test_audit_verify_endpoint.py:49-91 still hashes rows with the old three-field form

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the reply was discarded: checked openspec/changes/audit-verifiable/tasks.md:75 does not resolve
- **Blocking tasks:** 2.2
- **Kind:** technical
- **Asked:** 2026-10-26T18:03Z by deepseek, run r-20261026T1730Z-c15c, task 2.2

### Context
Task 2.2 says to change this file's helpers so `_build_chain_rows` returns rows with all 13 columns hashed via `canonical_event_fields`/`canonical_json_bytes`/`chain_hash`/`genesis_hash`, but the red commit left it unchanged: it builds `MagicMock` rows with only seven attributes and a hash over `{event_type, tenant_id, payload}`. The spec and design require the endpoint to verify the canonical nine hashed fields through `verify_events(chain_event_from_row(row))`, so `test_verify_chain_ok` (line 139), `test_verify_chain_tampered` (line 163) and `test_verify_chain_tenant_id_param` (line 222) can only pass against the old three-field verifier that this change removes. Green may not edit tests (the harness restores the file), so the two directives contradict each other.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/unit/admin_api/test_audit_verify_endpoint.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit audit-chain-verifiable`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/unit/admin_api/test_audit_verify_endpoint.py`: replace `_GENESIS_PREFIX`, `_genesis_hash`, `_compute_event_hash` and `_build_chain_rows` (lines 49-82) so `_build_chain_rows` returns `types.SimpleNamespace` rows with all 13 columns (`id` `f"audit_evt_{i:03d}"`, `tenant_id`, `event_type` `"test.event"`, `actor_id` `None`, `actor_type` `"system"`, `target_id`/`target_type` `None`, `payload` `{"seq": i}`, `at` `datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i)`, `request_id`/`trace_id` `None`) and computes `hash` as `chain_hash(canonical_json_bytes(canonical_event_fields(...)), prev)` imported from `mintkey_models.audit_hash`; test bodies unchanged.
2. Unfreeze `tests/unit/admin_api/test_audit_verify_endpoint.py` for this green step and I will make exactly the helper change task 2.2 describes.

### Clarifier suggestion
Edit `tests/unit/admin_api/test_audit_verify_endpoint.py`: replace `_GENESIS_PREFIX`, `_genesis_hash`, `_compute_event_hash` and `_build_chain_rows` (lines 49-82) so `_build_chain_rows` returns `types.SimpleNamespace` rows with all 13 columns (`id` `f"audit_evt_{i:03d}"`, `tenant_id`, `event_type` `"test.event"`, `actor_id` `None`, `actor_type` `"system"`, `target_id`/`target_type` `None`, `payload` `{"seq": i}`, `at` `datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i)`, `request_id`/`trace_id` `None`) and computes `hash` as `chain_hash(canonical_json_bytes(canonical_event_fields(...)), prev)` imported from `mintkey_models.audit_hash`; test bodies unchanged.

### Answer
<!-- write below this line -->
Option 1, as task 2.2 and proposal.md (Changed tests, set-up only) say: unfreeze tests/unit/admin_api/test_audit_verify_endpoint.py for the green of 2.2 and change only its helpers. Remove _GENESIS_PREFIX, _genesis_hash and _compute_event_hash; _build_chain_rows returns types.SimpleNamespace rows with all 13 columns (id f"audit_evt_{i:03d}", tenant_id, event_type "test.event", actor_id None, actor_type "system", target_id and target_type None, payload {"seq": i}, at datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i), request_id and trace_id None, prev_hash, hash), the first prev_hash being genesis_hash(str(tenant_id)) and each hash chain_hash(canonical_json_bytes(canonical_event_fields(...)), prev_hash), all imported from mintkey_models.audit_hash. The test bodies stay unchanged. (Answered by the owner's delegate.)
