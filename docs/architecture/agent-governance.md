# Agent governance

This note describes the model that Mintkey uses to let human operators and autonomous agents share the third-party services an organisation has connected. It is background only: the normative requirements live in the OpenSpec changes, and this page gives the vocabulary and the shape of the model those changes build on so that the later work reads as one story.

## Terms

| Term | Meaning |
|---|---|
| Operator | A human user of the Admin Console who belongs to a tenant. |
| Agent | An autonomous program that holds an Agent API key and calls MCP and the egress proxy. |
| Service | A third-party API that an operator has registered with Mintkey. |
| Credential | The secret a Service accepts, stored encrypted by the Vault Adapter. |
| Grant | Permission for one agent to reach one Service for a period. |
| Owner | The operator or agent that holds a Service. |
| Access request | A pending ask from an agent for a Grant on a Service. |
| Publisher | The role of an agent that owns Services. |
| Consumer | The role of an agent that uses Services it does not own. |

## Roles and operations

Every agent has one of two roles. A consumer asks for access to the Services it needs and reads its own access requests, and it sees only the grants and budgets that concern it. A publisher does everything a consumer does and also creates and updates the Services it owns, sets their credentials, and grants other agents access to them.

Some operations belong to human operators alone. No agent deletes a Service, transfers ownership of a Service, sets another agent's role, or reads a credential. Those actions stay with an operator in the Admin Console.

## Ownership and grants

A Service is owned by an operator or by a single agent. Ownership moves only when an operator transfers it, never by an agent action. A Grant records the agent, the Service, the optional expiry, and the operator or agent that granted it; revocation is immediate and reaches the egress proxy so that the next request through it is refused.

## Access requests

A requester opens at most one pending access request per Service. The owner of the Service or any operator decides the request. Approval turns it into a Grant with a bounded lifetime, so that access does not accumulate silently; a refused or expired request leaves the requester with no access.

## Agent-supplied targets

When an agent supplies a target URL for a Service, only `https` addresses that resolve to public hosts are accepted. The check runs when the target is stored and again when the egress proxy connects, so a hostname that later moves to a private address is not followed.

## Where it lives

| Part of the model | Location in this repository |
|---|---|
| Agent-facing routes (`/v1/agent`) and operator routes | `apps/admin-api/src/admin_api/api/` |
| Tenant session and role checks | `apps/admin-api/src/admin_api/auth/sessions.py` |
| MCP tools an agent discovers | `apps/mcp-server/src/mcp_server/tools/` |
| Credential storage and encryption | `apps/vault-adapter/` |
| Credential injection on egress | `apps/proxy-plugin/` |
| Short-lived token issuance | `apps/broker/` |
| Operator console | `apps/admin-ui/` |
