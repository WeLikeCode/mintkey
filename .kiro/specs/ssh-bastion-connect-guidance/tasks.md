# SSH Bastion Connect Guidance + Auth Observability — Tasks

Mirrors `openspec/changes/ssh-bastion-connect-guidance/tasks.md`; each task cites R#.AC#.

Status: implemented on `main` by PR #274 (97a9ae8): the `ssh_connect.hint` of
`apps/mcp-server/src/mcp_server/tools/request_token.py` (tested in `apps/mcp-server/tests/test_request_token.py`),
`metrics.RecordAuthFailure` and the `ssh.auth.failed` Warn log in `apps/ssh-proxy/internal/server/server.go`,
`LOG_LEVEL` in `apps/ssh-proxy/cmd/ssh-proxy/main.go` (Go tests beside each), and ADR-0032. `_Requirements:_` lines
map each task to the acceptance criteria (Req N.M) of `requirements.md`, from the task's own R#.AC# reference.

## 1. ADR
- [x] 1.1 ADR-0032 + `adrs/` symlink + `adr/README.md` row (amends ADR-0022). [docs]
- [x] 1.2 `openspec validate ssh-bastion-connect-guidance --strict`. [chore]

## 2. mcp-server (Python)
- [x] 2.1 Enrich `ssh_connect.hint` in `tools/request_token.py`. (R1.1, R1.2)
  - _Requirements: 1.1, 1.2_
- [x] 2.2 Unit test asserting hint names ssh_user + token, warns off mk_agent key. (R1.1)
  - _Requirements: 1.1_

## 3. ssh-proxy (Go)
- [x] 3.1 Warn-log + `RecordAuthFailure()` on failed JWT/pubkey auth; no credential bytes. (R2.1, R2.2)
  - _Requirements: 2.1, 2.2_
- [x] 3.2 Wire `LOG_LEVEL` → slog level (default info). (R3.1)
  - _Requirements: 3.1_
- [x] 3.3 Go unit: failed auth → Warn + metric; LOG_LEVEL=debug enables debug. (R2, R3)
  - _Requirements: 2.1, 2.2, 3.1_

## 4. Verify & PR
- [x] 4.1 mcp-server pytest + ruff/mypy; ssh-proxy `go test ./...` + `go vet`. [chore]
- [x] 4.2 PR to `main` with pasted verification output (no contract files touched). [chore]
