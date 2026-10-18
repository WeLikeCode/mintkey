# Design — SSH Bastion Connect Guidance + Auth Observability

## Context
Bastion auth (ADR-0022) validates a broker JWT presented as the SSH password against the SSH
username (`ssh_connect.ssh_user`). Field incidents traced to agents substituting the username or
using their `mk_agent` key as the password; failures were invisible (logged at unwired `slog.Debug`).

## Decisions
### D1 — Guidance in `request_token`
Enrich only the `hint` string built in `apps/mcp-server/src/mcp_server/tools/request_token.py`
(the block that assembles `ssh_connect`). Do not add/rename fields → no contract impact.

### D2 — Warn-level failure logging + metric
In `apps/ssh-proxy/internal/server/server.go` `passwordCallback`/`publicKeyCallback`, change the
failure `slog.Debug` to `slog.Warn` (keep `user`, add a short reason; never log the credential
bytes) and call the existing `metrics.RecordAuthFailure()` (see `internal/metrics/metrics.go`).

### D3 — Wire LOG_LEVEL → slog
At bastion startup (ssh-proxy `cmd`/server bootstrap), parse `LOG_LEVEL` and set the slog handler
level, so `debug`/`info`/`warn`/`error` take effect.

## Testing strategy
- mcp-server unit: assert the SSH `ssh_connect.hint` contains "ssh_user" (verbatim username) and
  names this response's `token` as the password (and warns off the `mk_agent` key).
- ssh-proxy Go unit: a `passwordCallback` with a bad token logs at Warn and increments
  `AuthFailures`; a `LOG_LEVEL=debug` bootstrap yields a debug-enabled handler.

## Risks & mitigations
- **Log a secret by accident**: assert only `user` + reason are logged, never password/JWT bytes;
  reviewer checks the log call sites.
- **LOG_LEVEL parse regression**: default to `info` on unknown values.
