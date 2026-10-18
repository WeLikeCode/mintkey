# SSH Bastion — Connect Guidance + Auth-Failure Observability

## Why
Agents (observed with a live cluster agent) repeatedly hit an opaque `Permission denied` against
the SSH bastion for one of two reasons: (1) they log in with the wrong SSH **username** instead of
`ssh_connect.ssh_user`, or (2) they present their long-lived `mk_agent` MCP key as the SSH
**password** instead of the short-lived `request_token` JWT. The bastion logs the reason only at
`slog.Debug` and `LOG_LEVEL` is not wired into the slog level, so operators cannot see the failure
at all — despite an existing `AuthFailures` metric. Result: long debugging loops and mis-diagnoses
(e.g. a suspected "JWKS sync" issue that was actually a client-side username/token mistake).

## What Changes
- **mcp-server** (`tools/request_token.py`): enrich `ssh_connect.hint` to state, unambiguously —
  username = `ssh_connect.ssh_user` verbatim (do not substitute); password = this response's
  `token` (the JWT), NOT your `mk_agent` key / `Bearer` string; `PreferredAuthentications=password`,
  `PubkeyAuthentication=no`; fresh per request, ~10-min TTL, single-use. **No wire-schema change.**
- **ssh-proxy** (`server.go`): log failed JWT + public-key auth at `slog.Warn` (with `user` +
  redacted reason) and increment `metrics.RecordAuthFailure()`; wire `LOG_LEVEL` into the slog
  handler level so verbosity control actually works.

## Capabilities
### New Capabilities
- `ssh-bastion-observability`: operators can observe SSH bastion auth failures (log + metric); agents
  receive unambiguous connect guidance in every token response.

## Impact
- **Services**: mcp-server (`tools/request_token.py`, string only); ssh-proxy
  (`internal/server/server.go` + logger wiring in `cmd`).
- **Contracts**: none — `ssh_connect` is not a fixed-value contract field (verified: no schema entry
  pins `hint`); no OpenAPI/event-schema change.
- **ADR**: `0032-ssh-bastion-connect-guidance-and-auth-observability.md` (amends ADR-0022).
- **Tests**: mcp-server unit assert the hint contains the username/token guidance; ssh-proxy unit
  assert a failed auth logs at Warn + increments the metric.
- **Out of scope**: any change to the bastion auth *mechanism* (ADR-0022 stands); no new endpoints.

## Issue Intake (remediation gate)
1. **Problem statement**: Agents can't tell why bastion SSH fails; operators can't see the failures.
2. **User-visible symptom**: `Permission denied` with no logs; mis-diagnosed as a broker/JWKS issue.
3. **Expected behavior**: Token response guidance prevents the username/token mistakes; failures are
   logged (Warn) + counted for operators.
4. **Evidence**: Reproduced 2026-07-16 — correct `ssh_user`+JWT succeeds; wrong username or
   `mk_agent`-key-as-password both yield `Permission denied`; failure logged only at unwired Debug.
5. **Scope**: request_token hint string; ssh-proxy Warn log + metric + LOG_LEVEL wiring; ADR-0032; tests.
6. **Out of scope**: auth mechanism; contract.
7. **Risk level**: LOW — guidance string + logging/observability; no behavior/authz change.
8. **Verification target**: mcp-server + ssh-proxy unit tests green; a failed bastion auth emits a
   Warn line + increments AuthFailures; `LOG_LEVEL` changes verbosity.
9. **Owner decisions**: none outstanding (contract-free, no wire change).
