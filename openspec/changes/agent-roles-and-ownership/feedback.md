# Feedback — agent-roles-and-ownership

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | withdrawn | behaviour |  | The transfer and role answers show the state after the change |
| FB-002 | addressed | behaviour |  | agent.role.changed names the agent in its wire form |
<!-- l4:feedback-index:end -->

---

## FB-001: The transfer and role answers show the state after the change

- **Status:** withdrawn
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T05:05:11Z

### Feedback
transfer_service_ownership answers with the row it selected before its UPDATE, so the body still shows the previous owner, the previous updated_at and current_key_version 0 (the transfer SELECT lacks the key-version subquery). The role PATCH patches only role into the old row, so its updated_at is the previous one. Build both answers from the stored state after the update (for example select the row again in the same transaction). In _service_row_to_dict, read row.current_key_version again instead of getattr(..., 0), so a SELECT without that column fails instead of answering 0.

### When / Then
- **When:** an operator transfers a service that has a credential to an active publisher, or back to operators, or changes an agent's role
- **Then:** the 200 body shows the service or agent as stored after the change: the new owner_agent_id, the service's current key version and the updated_at of the change for a transfer, and the new role and the updated_at of the change for a role PATCH

### Outcome
<!-- written by the harness -->
Taken in round 4 into agent-roles-and-ownership-fix-3

---

## FB-002: agent.role.changed names the agent in its wire form

- **Status:** addressed
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T05:05:12Z

### Feedback
update_agent_role writes the path id as given into the payload; service.ownership_transferred already converts with db_uuid_to_wire, and agent.role.changed should do the same.

### When / Then
- **When:** an operator changes an agent's role and names the agent in the path by its UUID or by a legacy wire id
- **Then:** the agent.role.changed audit event's agent_id is the agent's canonical wire id (agent_ followed by 26 characters), as the event's schema requires

### Outcome
<!-- written by the harness -->
Addressed in round 6 at 602993c7b4: apps/admin-api/src/admin_api/api/agents.py update_agent_role payload uses db_uuid_to_wire(agent_uuid, "agent"); tests in test_role_event_wire_id.py
