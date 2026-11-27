# Spec Delta

## Purpose
An agent has a role that an operator sets, a service has an owner that is an agent or the operators, and only an operator changes either. This capability is the data and the operator routes; the agent-side operations that read them are specified where they are given.

## ADDED Requirements

### Requirement: The transfer and role answers show the state after the change — feedback FB-001
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: The transfer and role answers show the state after the change
- **WHEN** an operator transfers a service that has a credential to an active publisher, or back to operators, or changes an agent's role
- **THEN** the 200 body shows the service or agent as stored after the change: the new owner_agent_id, the service's current key version and the updated_at of the change for a transfer, and the new role and the updated_at of the change for a role PATCH

### Requirement: agent.role.changed names the agent in its wire form — feedback FB-002
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: agent.role.changed names the agent in its wire form
- **WHEN** an operator changes an agent's role and names the agent in the path by its UUID or by a legacy wire id
- **THEN** the agent.role.changed audit event's agent_id is the agent's canonical wire id (agent_ followed by 26 characters), as the event's schema requires
