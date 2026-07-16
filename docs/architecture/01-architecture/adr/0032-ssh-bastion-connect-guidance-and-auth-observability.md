# ADR-0032: SSH bastion — agent connect-guidance + auth-failure observability

## Status
Proposed — 2026-07-16

## Context
The SSH bastion (ADR-0022) authenticates an agent by validating the broker-issued JWT presented
as the SSH password, keyed to the SSH **username** (which must equal the agent id returned in
`request_token`'s `ssh_connect.ssh_user`). Two recurring agent-side mistakes both surface as an
opaque `Permission denied`, with no operator-visible signal:

1. **Username substitution** — the agent logs in as something other than `ssh_connect.ssh_user`
   (e.g. the `agent_…` wire id, the service slug, or the target user `superpsuser`). The bastion
   rejects because the username doesn't match the JWT subject.
2. **Wrong password token** — the agent presents its long-lived `mk_agent` MCP key (or the
   `Bearer mk_agent…` string) as the SSH password instead of the short-lived `request_token` JWT
   (`resp.token`). The bastion can't validate it as a JWT.

Both were reproduced with a real agent's key (an in-cluster agent landed successfully only with
the correct `ssh_user` + JWT). The bastion logs the failure reason at `slog.Debug`
(`server.go` `passwordCallback`/`publicKeyCallback`), and `LOG_LEVEL` is **not** wired into the
slog level — so even `LOG_LEVEL=debug` emits nothing and operators cannot see why an agent failed,
despite an existing `AuthFailures` metric.

## Decision
1. **Enrich `ssh_connect.hint`** (mcp-server `tools/request_token.py`) so every SSH token response
   states, unambiguously: use `ssh_connect.ssh_user` **verbatim** as the SSH username (do not
   substitute the agent/service/target name); the SSH **password is this response's `token`** (the
   short-lived JWT), **not** your `mk_agent` key / `Bearer` string; use
   `-o PreferredAuthentications=password -o PubkeyAuthentication=no`; the token is fresh per request,
   ~10-min TTL, single-use. This is a **string/guidance change only — no wire-schema change**.
2. **Surface auth failures** (ssh-proxy `server.go`): log failed JWT and public-key auth at
   `slog.Warn` with `user` and a redacted `reason`, and increment the existing
   `metrics.RecordAuthFailure()` counter. No secret material (password/JWT bytes) is logged.
3. **Wire `LOG_LEVEL` into the slog level** (ssh-proxy startup) so `LOG_LEVEL=debug|info|warn|error`
   actually controls verbosity (fixing the silent no-op observed in the field).

## Consequences
- Agents get actionable connect guidance at the point of use → fewer opaque `Permission denied`
  loops. No API/contract change (the `ssh_connect` object is not a fixed-value contract field).
- Operators can see and alert on auth failures (log + metric) without shell access to the pod.
- Small, self-contained: touches `apps/mcp-server/src/mcp_server/tools/request_token.py` and
  `apps/ssh-proxy/internal/server/server.go` (+ its logger wiring); adds unit assertions.

## Alternatives considered
| Option | Why not |
|---|---|
| Have the bastion accept the `mk_agent` key directly as SSH password | Defeats the short-lived-token design (ADR-0022); long-lived secret over SSH. |
| Only fix the hint, not the logging | Leaves operators blind to the next agent's failure. |
| Rely on the per-service `description` recipe (already added live) | Not every agent reads the description; the hint is per-request and universal. |

## Related
- [ADR-0022](0022-ssh-bastion.md) — SSH bastion (this ADR amends its agent-connect UX + observability).
- OpenSpec: `openspec/changes/ssh-bastion-connect-guidance/`; Kiro: `.kiro/specs/ssh-bastion-connect-guidance/`.
