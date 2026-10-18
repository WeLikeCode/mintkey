# SSH Bastion Connect Guidance + Auth Observability — Design

See ADR-0032 and `openspec/changes/ssh-bastion-connect-guidance/design.md`. Summary:

- **mcp-server** `apps/mcp-server/src/mcp_server/tools/request_token.py`: enrich the `hint` string in
  the `ssh_connect` block (R1). String-only; no schema change.
- **ssh-proxy** `apps/ssh-proxy/internal/server/server.go`: `passwordCallback` + `publicKeyCallback`
  log failures at `slog.Warn` (user + redacted reason) and call `metrics.RecordAuthFailure()`
  (`internal/metrics/metrics.go`) (R2); wire `LOG_LEVEL` → slog handler level at startup (R3).
- **Tests**: mcp-server unit asserts hint content; ssh-proxy Go unit asserts Warn + metric on failed
  auth and LOG_LEVEL parsing.
- **Security**: never log credential bytes (R2.2) — reviewer verifies each log call site.
