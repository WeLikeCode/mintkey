# Tasks — SSH Bastion Connect Guidance + Auth Observability

## 1. ADR
- [x] 1.1 ADR-0032 (Proposed) + `adrs/` symlink + `adr/README.md` index row. (amends ADR-0022)
- [x] 1.2 `openspec validate ssh-bastion-connect-guidance --strict`.

## 2. mcp-server (Python)
- [x] 2.1 Enrich `ssh_connect.hint` in `tools/request_token.py`: username = ssh_user verbatim;
      password = this response's `token` (NOT the mk_agent key/Bearer); PreferredAuthentications=password,
      PubkeyAuthentication=no; fresh/single-use ~10-min TTL. (R1)
- [x] 2.2 Unit test asserting the hint content. (R1)

## 3. ssh-proxy (Go)
- [x] 3.1 `server.go` passwordCallback + publicKeyCallback: `slog.Warn` on failure with user + reason;
      call `metrics.RecordAuthFailure()`. Never log credential bytes. (R2)
- [x] 3.2 Wire `LOG_LEVEL` env → slog handler level at startup (default info). (R3)
- [x] 3.3 Go unit: failed auth → Warn + AuthFailures incremented; LOG_LEVEL=debug enables debug. (R2,R3)

## 4. Verify
- [x] 4.1 mcp-server pytest + ruff/mypy green; ssh-proxy `go test ./...` + `go vet` green.
- [x] 4.2 Open PR to `main` (no contract files → no contracts CODEOWNERS gate) with pasted output.
