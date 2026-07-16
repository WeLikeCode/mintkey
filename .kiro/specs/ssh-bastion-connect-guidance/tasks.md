# SSH Bastion Connect Guidance + Auth Observability — Tasks

Mirrors `openspec/changes/ssh-bastion-connect-guidance/tasks.md`; each task cites R#.AC#.

## 1. ADR
- [ ] 1.1 ADR-0032 + `adrs/` symlink + `adr/README.md` row (amends ADR-0022).
- [ ] 1.2 `openspec validate ssh-bastion-connect-guidance --strict`.

## 2. mcp-server (Python)
- [ ] 2.1 Enrich `ssh_connect.hint` in `tools/request_token.py`. (R1.1, R1.2)
- [ ] 2.2 Unit test asserting hint names ssh_user + token, warns off mk_agent key. (R1.1)

## 3. ssh-proxy (Go)
- [ ] 3.1 Warn-log + `RecordAuthFailure()` on failed JWT/pubkey auth; no credential bytes. (R2.1, R2.2)
- [ ] 3.2 Wire `LOG_LEVEL` → slog level (default info). (R3.1)
- [ ] 3.3 Go unit: failed auth → Warn + metric; LOG_LEVEL=debug enables debug. (R2, R3)

## 4. Verify & PR
- [ ] 4.1 mcp-server pytest + ruff/mypy; ssh-proxy `go test ./...` + `go vet`.
- [ ] 4.2 PR to `main` with pasted verification output (no contract files touched).
