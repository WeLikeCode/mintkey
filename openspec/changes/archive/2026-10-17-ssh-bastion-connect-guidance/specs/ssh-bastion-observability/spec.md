# SSH Bastion Observability & Connect Guidance

## ADDED Requirements

### Requirement: request_token SSH guidance is unambiguous
`request_token` responses for SSH services SHALL include an `ssh_connect.hint` that states the SSH
username is `ssh_connect.ssh_user` used verbatim, and the SSH password is the same response's
`token` (a short-lived JWT) and NOT the agent's `mk_agent` key or `Bearer` string, along with the
`PreferredAuthentications=password` / `PubkeyAuthentication=no` options and the single-use / ~10-min
TTL nature of the token. This is a guidance-text change only; the `ssh_connect` shape is unchanged.

#### Scenario: Hint names the token as the password
- **WHEN** an agent calls `request_token` for an SSH service
- **THEN** the returned `ssh_connect.hint` references `ssh_user` as the login user and this
  response's `token` as the password, and warns against using the `mk_agent` key

### Requirement: Bastion auth failures are observable
The SSH bastion SHALL log every failed JWT or public-key authentication at `Warn` level with the
presented `user` and a redacted `reason`, and SHALL increment the `AuthFailures` metric. No secret
material (password bytes, JWT) is logged.

#### Scenario: Failed auth is visible
- **WHEN** an agent presents a wrong username or a non-JWT password
- **THEN** the bastion emits a `Warn` log line with the username + reason and increments the
  `AuthFailures` counter, while still returning `Permission denied` to the client

### Requirement: LOG_LEVEL controls bastion verbosity
The SSH bastion SHALL map the `LOG_LEVEL` environment variable (`debug|info|warn|error`) to the slog
handler level at startup, so operators can raise or lower verbosity.

#### Scenario: Debug verbosity
- **WHEN** the bastion starts with `LOG_LEVEL=debug`
- **THEN** `slog.Debug` lines are emitted (previously suppressed regardless of `LOG_LEVEL`)
