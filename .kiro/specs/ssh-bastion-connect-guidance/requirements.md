# SSH Bastion Connect Guidance + Auth Observability — Requirements

## Status
Proposed — 2026-07-16. Traces to ADR-0032 (amends ADR-0022) and
`openspec/changes/ssh-bastion-connect-guidance/`.

## Introduction
Reduce opaque `Permission denied` failures at the SSH bastion by (a) giving agents unambiguous
connect guidance in every `request_token` response and (b) making bastion auth failures visible to
operators (log + metric), including fixing `LOG_LEVEL` wiring. No auth-mechanism or contract change.

## Glossary
- **ssh_user**: `ssh_connect.ssh_user` — the SSH username an agent MUST use verbatim (the agent id).
- **token**: `request_token` response `token` — the short-lived JWT used as the SSH password.
- **mk_agent key**: the agent's long-lived MCP bearer key (must NOT be used as the SSH password).

## Error Codes
- n/a (no new API surface).

## Requirements

### Requirement 1: Unambiguous SSH connect guidance
**User Story:** As an agent, I want the token response to tell me exactly how to connect, so that I
don't fail with `Permission denied`.

#### Acceptance Criteria
1. WHEN an agent calls `request_token` for an SSH service, THEN the mcp-server SHALL return an
   `ssh_connect.hint` that (a) names `ssh_connect.ssh_user` as the SSH username to use verbatim,
   (b) names this response's `token` as the SSH password, (c) explicitly warns NOT to use the
   `mk_agent` key / `Bearer` string as the password, and (d) includes
   `PreferredAuthentications=password` and `PubkeyAuthentication=no` and the single-use/~10-min-TTL note.
2. THE change SHALL NOT alter the `ssh_connect` object shape (no added/removed/renamed fields) and
   SHALL require no OpenAPI change.

### Requirement 2: Observable auth failures
**User Story:** As an operator, I want to see bastion auth failures, so that I can diagnose agents
without shell access.

#### Acceptance Criteria
1. WHEN a JWT or public-key authentication fails at the bastion, THEN the ssh-proxy SHALL log the
   event at `Warn` with the presented `user` and a redacted reason, and SHALL increment the
   `AuthFailures` metric.
2. THE bastion SHALL NOT log credential material (password bytes or the JWT) at any level.

### Requirement 3: LOG_LEVEL controls verbosity
**User Story:** As an operator, I want `LOG_LEVEL` to work, so that I can raise verbosity when needed.

#### Acceptance Criteria
1. WHEN the ssh-proxy starts with `LOG_LEVEL` set to `debug|info|warn|error`, THEN it SHALL configure
   the slog handler to that level; on an unknown value it SHALL default to `info`.
