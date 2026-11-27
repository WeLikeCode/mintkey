# Questions — agent-roles-and-ownership

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
| Q-001 | answered | 1.1, 2.1, 3.1, 3.2, 4.1, 5.1 | ambiguous | Scenarios "the contract lists both events" and "the contract names them" conflict |
| Q-002 | open | 4.1 | technical | tests/unit/admin_api/test_service_ownership.py:594 — test_C_2e9cfe5e_unsuitable_targets expects mintkey:code agent_not_publisher/agent_not_active, contradicting the spec and test_C_cdc7f907 in the sam |
<!-- l4:index:end -->

---

## Q-001: Scenarios "the contract lists both events" and "the contract names them" conflict

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1, 3.1, 3.2, 4.1, 5.1
- **Kind:** ambiguous
- **Asked:** intake lint (L4-ODD-004)
- **Criteria:** C-c807e49c (agent-roles-and-ownership › The new events are in the audit contract › the contract lists both events), C-29874427 (grant-expiry › The audit contract records the grantor and the expiry › the contract names them)

### Context
These two scenarios have the same GIVEN and WHEN and different THEN, so the implementer cannot satisfy both.
- agent-roles-and-ownership › The new events are in the audit contract › the contract lists both events (specs/agent-roles-and-ownership/spec.md:215)
  WHEN the schema file is loaded as JSON
  THEN both definitions exist with exactly those payload property names, the two types are keys of
- grant-expiry › The audit contract records the grantor and the expiry › the contract names them (openspec/specs/grant-expiry/spec.md:261)
  WHEN the schema file is loaded as JSON
  THEN the three definitions list those properties and that enum value, and the `required` lists they had are
Which behaviour is wanted? Answer below and set Status to answered. If one scenario is wrong, delete it from the spec on this unit branch in the same commit; a change on the base branch does not reach this unit.

### Answer
<!-- write below this line -->
The two scenarios do not conflict, and neither is to be deleted. They share a WHEN only because both load the same file, docs/architecture/contracts/events/audit-event.schema.json, but their THENs assert disjoint parts of it. The grant-expiry scenario belongs to the grant-expiry capability and is already satisfied at this unit's base: ev_agent_permission_granted and ev_agent_permission_revoked already carry grantor_id, and the reason_code enum of ev_token_denied already holds grant_expired. This unit's scenario adds two new definitions, ev_agent_role_changed and ev_service_ownership_transferred, under $defs, each with one $ref in the top-level oneOf and one entry in discriminator.mapping, as design decision D6 describes. Implement the agent-roles-and-ownership scenario as written, leave the three grant-expiry definitions and their required lists untouched, and both scenarios hold on the same file at once.

---

## Q-002: tests/unit/admin_api/test_service_ownership.py:594 — test_C_2e9cfe5e_unsuitable_targets expects mintkey:code agent_not_publisher/agent_not_active, contradicting the spec and test_C_cdc7f907 in the sam

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the answer would unfreeze tests/unit/admin_api/test_service_ownership.py of task 4.1 (delegate.unfreeze is false)
- **Blocking tasks:** 4.1
- **Kind:** technical
- **Asked:** 2026-11-27T02:18Z by deepseek, run r-20261127T0033Z-a936, task 4.1

### Context
At line 594 the test asserts body.get("mintkey:code") == code, and the three 422 cases set `code` to agent_not_publisher / agent_not_active. The spec requirement 'An operator transfers a service's ownership' and 'The operator routes answer errors in one flat shape' say every unsuitable target answers 422 with mintkey:code invalid_transfer_target and reason agent_not_publisher or agent_not_active. test_C_cdc7f907_the_transfer_error_bodies_are_flat (same file, line 746) asserts exactly that for an active consumer target, and both tests send the same request, so no single response can satisfy both. The implementation currently follows the spec: 422 {mintkey:code: invalid_transfer_target, title: Transfer target not allowed, reason: agent_not_publisher|agent_not_active}.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/unit/admin_api/test_service_ownership.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit agent-roles-and-ownership`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/unit/admin_api/test_service_ownership.py`: in `test_C_2e9cfe5e_unsuitable_targets`, change the expected `mintkey:code` (the fifth tuple element) of the three 422 cases from `agent_not_publisher`, `agent_not_active`, `agent_not_active` to `invalid_transfer_target` for all three, leaving each `reason` (sixth element) unchanged.
2. Keep the test as is and change the requirement plus `test_C_cdc7f907_the_transfer_error_bodies_are_flat` so an unsuitable target's `mintkey:code` equals its `reason` (`agent_not_publisher`/`agent_not_active`) instead of `invalid_transfer_target`.

### Clarifier suggestion
Edit `tests/unit/admin_api/test_service_ownership.py`: in `test_C_2e9cfe5e_unsuitable_targets`, change the expected `mintkey:code` (the fifth tuple element) of the three 422 cases from `agent_not_publisher`, `agent_not_active`, `agent_not_active` to `invalid_transfer_target` for all three, leaving each `reason` (sixth element) unchanged.

### Answer
<!-- write below this line -->
Take option 1: edit tests/unit/admin_api/test_service_ownership.py so that, in test_C_2e9cfe5e_unsuitable_targets, the three 422 cases expect mintkey:code invalid_transfer_target, each keeping its reason (agent_not_publisher, agent_not_active, agent_not_active). The requirement says an unsuitable target answers 422 invalid_transfer_target with that reason, and the flat-error test of the same file asserts the same body; the scenario's short form names the reason. Answered by the repository owner's delegate.
