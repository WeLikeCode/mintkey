# Questions — agent-service-routes

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
| Q-001 | answered | 6.1 | technical | tests/unit/admin_api/test_agent_routes_isolation.py:295 needs tests/acceptance/openapi_snapshot.json unfrozen to add "agent": "/v1/agent" |
| Q-002 | open | none | verdict | Criterion C-4b7e8c8f (agent-service-credential › A credential is written, never read, and bound to its target › a bearer credential): accept as satisfied? |
| Q-003 | open | none | verdict | Criterion C-3be566fb (agent-service-credential › A credential is written, never read, and bound to its target › header and query names): accept as satisfied? |
| Q-004 | open | none | verdict | Criterion C-08831467 (agent-service-credential › A credential is written, never read, and bound to its target › bad values, other owners, a failing vault, an unsupported scheme): accept as satisfied? |
| Q-005 | open | none | verdict | Criterion C-6d26cd39 (agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write): accept as satisfied? |
| Q-006 | open | none | verdict | Criterion C-50c7880c (agent-service-credential › service.credential.set matches its schema — feedback FB-003 › service.credential.set matches its schema): accept as satisfied? |
| Q-007 | open | none | verdict | Hold H-0567faca: scope: `packages/python/mintkey-models/mintkey_models/egress.py` changes module `python`, which the spec does not name |
<!-- l4:index:end -->

---

## Q-001: tests/unit/admin_api/test_agent_routes_isolation.py:295 needs tests/acceptance/openapi_snapshot.json unfrozen to add "agent": "/v1/agent"

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the answer would unfreeze tests/acceptance/openapi_snapshot.json of task 6.1 (delegate.unfreeze is false)
- **Blocking tasks:** 6.1
- **Kind:** technical
- **Asked:** 2026-11-27T22:11Z by deepseek, run r-20261127T2004Z-3d36, task 6.1

### Context
The frozen test asserts at line 295 that the snapshot maps "agent" to "/v1/agent", and tests/acceptance/test_openapi_parity.py::test_openapi_parity_snapshot compares the whole router map to the same snapshot. Task 6.1 and design D9 say to add exactly that entry to tests/acceptance/openapi_snapshot.json, but the green step's test-path freeze reverts any edit to that file, so both tests fail while every other gate test passes. The red step did not include the fixture entry.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/acceptance/openapi_snapshot.json`, `tests/acceptance/test_openapi_parity.py`, `tests/unit/admin_api/test_agent_routes_isolation.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit agent-service-routes`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/acceptance/openapi_snapshot.json`: add exactly the entry `"agent": "/v1/agent"` (in key order, before `"agent_secrets"`) and change no other line.
2. Leave the snapshot frozen: accept that `test_C_48021709_agent_route_table_and_snapshot` and `test_openapi_parity_snapshot` stay red for this task.

### Harness notes
Harness note: the previous attempt of this task was rejected: red tests still failing: tests.unit.admin_api.test_agent_routes_isolation::test_C_48021709_agent_route_table_and_snapshot
E       AssertionError: {'agent_secrets': '/v1/tenants/{tenant_id}/agent-secrets', 'agents': '/v1/tenants/{tenant_id}/agents', 'api_keys': '/v1/tenants/{tenant_id}/agents/{agent_id}/api-keys', 'audit': '/v1/tenants/{tenant_id}/audit', ...}
E       assert None == '/v1/agent'
E        +  where None = <built-in method get of dict object at 0x7f8ac44ba380>('agent')
E        +    where <built-in method get of dict object at 0x7f8ac44ba380> = {'agent_secrets': '/v1/tenants/{tenant_id}/agent-secrets', 'agents': '/v1/tenants/{tenant_id}/age
../../tests/unit/admin_api/test_agent_routes_isolation.py:295

### Clarifier suggestion
Edit `tests/acceptance/openapi_snapshot.json`: add exactly the entry `"agent": "/v1/agent"` (in key order, before `"agent_secrets"`) and change no other line.

### Answer
<!-- write below this line -->
Take option 1: edit tests/acceptance/openapi_snapshot.json and add exactly the entry "agent": "/v1/agent", in key order before "agent_secrets", changing no other line, as task 6.1 and design D9 say. Answered by the repository owner's delegate.

---

## Q-002: Criterion C-4b7e8c8f (agent-service-credential › A credential is written, never read, and bound to its target › a bearer credential): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 7, verifier
- **Criteria:** C-4b7e8c8f (agent-service-credential › A credential is written, never read, and bound to its target › a bearer credential)

### Context
Criterion C-4b7e8c8f (agent-service-credential › A credential is written, never read, and bound to its target › a bearer credential) is needs human after round 7.

Scenario:
\- **WHEN** a publisher puts the value `s3cret-value-123` on an owned `bearer_token` service
\- **THEN** `put_credential` was called once with that value as `plaintext`, the base URL as `target_url` and `egress_scope`
  `public`, and no statement names `egress_scope`; the answer has exactly the three keys, with the `updated_at` bound in the `services` UPDATE; one `mintkey:credential` NOTIFY `credential.registered` was sent; and the text of the
  response, of the NOTIFY, of every `audit_emit` call and of every statement and its parameters does not contain `s3cret-value-123`

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: tests.unit.admin_api.test_agent_credential::test_C_4b7e8c8f_bearer_credential_is_written_and_never_echoed (passed, zero_value)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
To set the check the fix must pass, end the reason with one sentence WHEN <the situation> THEN <the behaviour you expect>, with WHEN and THEN in capitals: it becomes a scenario of the fix unit. Without one, the fix is checked against the scenario above as it is written.

### Options
1. accept
2. reject: <reason>, then WHEN ... THEN ... to set the check

### Answer
<!-- write below this line -->
accept The tracing test test_C_4b7e8c8f_bearer_credential_is_written_and_never_echoed passes with a zero-value proof and asserts the scenario: one put_credential call with the value as plaintext, the base URL as target_url and egress_scope public, no statement naming egress_scope, exactly the three answer keys, and the secret absent from the answer, the NOTIFY, the audit calls and every statement. Answered by the repository owner's delegate.
---

## Q-003: Criterion C-3be566fb (agent-service-credential › A credential is written, never read, and bound to its target › header and query names): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 7, verifier
- **Criteria:** C-3be566fb (agent-service-credential › A credential is written, never read, and bound to its target › header and query names)

### Context
Criterion C-3be566fb (agent-service-credential › A credential is written, never read, and bound to its target › header and query names) is needs human after round 7.

Scenario:
\- **WHEN** an `api_key_header` service gets no `header_name`, `Host`, `X-Mintkey-Test`, then `X-Api-Key`; a `bearer_token`
  service gets a `header_name`; an `api_key_query` service gets no `query_param`
\- **THEN** all but the fourth answer 422 `mintkey:validation_failed`; the fourth answers 200 with `X-Api-Key` passed to
  `put_credential`

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_header] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[bearer_with_query] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_bad_characters] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_connection] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_content_length] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_host] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_missing] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_transfer_encoding] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_valid] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_x_mintkey] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[header_x_mintkey_lower] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[query_missing] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_3be566fb_header_and_query_names_follow_the_scheme[query_valid] (passed, zero_value)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
To set the check the fix must pass, end the reason with one sentence WHEN <the situation> THEN <the behaviour you expect>, with WHEN and THEN in capitals: it becomes a scenario of the fix unit. Without one, the fix is checked against the scenario above as it is written.

### Options
1. accept
2. reject: <reason>, then WHEN ... THEN ... to set the check

### Answer
<!-- write below this line -->
accept The parametrised tracing tests test_C_3be566fb_header_and_query_names_follow_the_scheme pass with zero-value proofs and cover each case of the scenario: a missing or reserved header name, a header name on a bearer service and a missing query parameter answer 422, and X-Api-Key reaches put_credential. Answered by the repository owner's delegate.
---

## Q-004: Criterion C-08831467 (agent-service-credential › A credential is written, never read, and bound to its target › bad values, other owners, a failing vault, an unsupported scheme): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 7, verifier
- **Criteria:** C-08831467 (agent-service-credential › A credential is written, never read, and bound to its target › bad values, other owners, a failing vault, an unsupported scheme)

### Context
Criterion C-08831467 (agent-service-credential › A credential is written, never read, and bound to its target › bad values, other owners, a failing vault, an unsupported scheme) is needs human after round 7.

Scenario:
\- **WHEN** the value is empty, 8193 characters long or `s3cret-value-123` plus a line feed; the service belongs to another
  agent; `put_credential` raises; or the service's scheme is `ssh_private_key`
\- **THEN** the answers have the bodies of that requirement and "Every error of the service routes has one body": 422 `mintkey:validation_failed` three times (no body contains `s3cret-value-123`), 403
  `mintkey:not_owner`, 502 `mintkey:vault_unavailable` and 422 `mintkey:validation_failed` with `field` `auth_scheme`; no
  metadata statement and no event ran, and `put_credential` was not called for the last

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[array] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[extra_key] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_body_shape_answers_422_without_a_write[unreadable_json] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[carriage_return] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[empty] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[line_feed] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[nul] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_bad_value_answers_422_without_a_write[too_long] (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_failing_vault_answers_502_before_metadata (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_other_owner_answers_403_without_a_write (passed, zero_value); tests.unit.admin_api.test_agent_credential::test_C_08831467_unsupported_scheme_answers_422_without_a_vault_call (passed, zero_value)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
To set the check the fix must pass, end the reason with one sentence WHEN <the situation> THEN <the behaviour you expect>, with WHEN and THEN in capitals: it becomes a scenario of the fix unit. Without one, the fix is checked against the scenario above as it is written.

### Options
1. accept
2. reject: <reason>, then WHEN ... THEN ... to set the check

### Answer
<!-- write below this line -->
accept The tracing tests test_C_08831467_* pass with zero-value proofs and cover the bad values, the other owner's service, the failing vault and the unsupported scheme with the bodies of the requirement, and they assert no metadata statement, no event and no put_credential call where the scenario says so. Answered by the repository owner's delegate.
---

## Q-005: Criterion C-6d26cd39 (agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 7, verifier
- **Criteria:** C-6d26cd39 (agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write)

### Context
Criterion C-6d26cd39 (agent-service-credential › A credential is written, never read, and bound to its target › the row is locked before the vault write) is needs human after round 7.

Scenario:
\- **WHEN** a publisher writes a credential on an owned service
\- **THEN** the first statement that names `services` after the tenant context contains `FOR UPDATE`, `put_credential` was
  called after it, and every metadata statement and `audit_emit` call came after `put_credential`

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: tests.unit.admin_api.test_agent_credential::test_C_6d26cd39_row_is_locked_before_the_vault_write (passed, zero_value)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
To set the check the fix must pass, end the reason with one sentence WHEN <the situation> THEN <the behaviour you expect>, with WHEN and THEN in capitals: it becomes a scenario of the fix unit. Without one, the fix is checked against the scenario above as it is written.

### Options
1. accept
2. reject: <reason>, then WHEN ... THEN ... to set the check

### Answer
<!-- write below this line -->
accept The tracing test test_C_6d26cd39_row_is_locked_before_the_vault_write passes with a zero-value proof and asserts the order of the scenario: the tenant context first, then the services statement with FOR UPDATE, then put_credential, and every metadata statement and audit call after it. Answered by the repository owner's delegate.
---

## Q-006: Criterion C-50c7880c (agent-service-credential › service.credential.set matches its schema — feedback FB-003 › service.credential.set matches its schema): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 7, verifier
- **Criteria:** C-50c7880c (agent-service-credential › service.credential.set matches its schema — feedback FB-003 › service.credential.set matches its schema)

### Context
Criterion C-50c7880c (agent-service-credential › service.credential.set matches its schema — feedback FB-003 › service.credential.set matches its schema) is needs human after round 7.

Scenario:
\- **WHEN** an agent sets the credential of a service it owns
\- **THEN** the service.credential.set audit event has target_type service and target_id the service's id, and the emitted event validates against its definition in audit-event.schema.json

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: tests.unit.admin_api.test_agent_credential_audit_event::test_C_50c7880c_credential_set_event_targets_the_service_and_validates (passed, red_assertion)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
To set the check the fix must pass, end the reason with one sentence WHEN <the situation> THEN <the behaviour you expect>, with WHEN and THEN in capitals: it becomes a scenario of the fix unit. Without one, the fix is checked against the scenario above as it is written.

### Options
1. accept
2. reject: <reason>, then WHEN ... THEN ... to set the check

### Answer
<!-- write below this line -->
accept The tracing test test_C_50c7880c_credential_set_event_targets_the_service_and_validates failed at red and passes now: the emitted service.credential.set event has target_type service and the service's id, and it validates against its definition in audit-event.schema.json. Answered by the repository owner's delegate.
---

## Q-007: Hold H-0567faca: scope: `packages/python/mintkey-models/mintkey_models/egress.py` changes module `python`, which the spec does not name

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 7, verifier

### Context
After round 7 the verifier cannot decide on its own: scope: `packages/python/mintkey-models/mintkey_models/egress.py` changes module `python`, which the spec does not name

Answer `accept` if the unit can go on as it stands, or `reject` and say why: a rejected hold is fixed by a fix unit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
accept The change to mintkey_models/egress.py is the one feedback FB-002 asked for: the target check waits for the resolver for at most RESOLVE_TIMEOUT_SECONDS and refuses a name still unresolved as unresolvable; nothing else in that module changed. Answered by the repository owner's delegate.
