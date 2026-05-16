# Network Reachability

Mintkey is a multi-service stack. Agents and AI clients reach Mintkey via two URLs:
the MCP server (port 8082) and the egress proxy (port 8000). Those URLs default to
`localhost` so `docker compose up` works without configuration. To use Mintkey from
another machine — LAN, VPN, or cloud — set the public URLs explicitly.

This document is the canonical reference for that configuration. It is intentionally
short. See [docs/HOW-TO.md](HOW-TO.md) for end-to-end agent flows; see
[docs/architecture/README.md](architecture/README.md) for the service map.

> **Status:** pre-alpha. Network configuration is operator-facing and may change.
> This document tracks the current implementation (commit chain NET-A → NET-E, 2026-05).

## TL;DR

Set two environment variables in `.env`:

```bash
MINTKEY_MCP_PUBLIC_URL=http://192.168.1.50:8082    # or https://mcp.example.com
MINTKEY_PROXY_PUBLIC_URL=http://192.168.1.50:8000  # or https://proxy.example.com
```

Run `docker compose up -d`. All bootstrap responses, dashboard snippets, and
`agent.mcp_endpoint` records will use those URLs. Existing agent rows are NOT
retroactively updated (the URL is snapshotted at creation time).

## Why two URLs

- **MCP URL** (`MINTKEY_MCP_PUBLIC_URL`) — what agents and AI clients use to call
  the MCP server (`/v1/tools/list`, `/v1/tools/call`, `/v1/agents/<id>`).
  Returned in the bootstrap response and persisted in `agents.mcp_endpoint`.

- **Proxy URL** (`MINTKEY_PROXY_PUBLIC_URL`) — what agents use to call the egress
  proxy (`/v1/call/<svc>/<path>`). Returned in `services.proxy_url` and in
  the `discover` tool's `how_to_call.proxy_url_pattern`.

They can be different. A cloud deployment might terminate TLS on two different
hostnames, or put the proxy behind one CDN and the MCP server on another.

## Precedence

For each URL, resolution checks env vars in this order, taking the first
non-empty value:

| Variable | Status |
|---|---|
| `MINTKEY_MCP_PUBLIC_URL` | canonical (recommended) |
| `MCP_BASE_URL` | legacy alias (logs deprecation warning) |
| `MINTKEY_MCP_URL` | legacy alias (logs deprecation warning) |
| _default_ | `http://localhost:8082` |

| Variable | Status |
|---|---|
| `MINTKEY_PROXY_PUBLIC_URL` | canonical (recommended) |
| `MINTKEY_PROXY_URL` | legacy alias (logs deprecation warning) |
| `KONG_PROXY_URL` | legacy alias (logs deprecation warning) |
| _default_ | `http://localhost:8000` |

Trailing slashes are stripped. Set one, the other, or both — defaults are
independent.

## LAN setup (single host)

1. Find the host's LAN IP (`ip addr | grep inet`).
2. Edit `.env`:

   ```bash
   MINTKEY_MCP_PUBLIC_URL=http://192.168.1.50:8082
   MINTKEY_PROXY_PUBLIC_URL=http://192.168.1.50:8000
   ```

3. `docker compose up -d`.
4. From another machine on the same network:
   - `curl http://192.168.1.50:8082/v1/tools/bootstrap` — bootstrap response
     shows `mcp_url` and `proxy_url` with the LAN address
   - Configure your AI client's MCP entry with `http://192.168.1.50:8082/v1`

> The default `0.0.0.0` listen interface for each container's port exposes them
> to the host's LAN already. If you want to bind to a specific interface for
> defense-in-depth, edit the `ports:` blocks in `docker-compose.yml` (e.g.
> `127.0.0.1:8082:8082`) — but that is outside this doc's scope.

## Cloud / TLS setup

Put each service behind a TLS-terminating reverse proxy (Caddy, nginx, ALB).
Mintkey accepts any URL scheme — it does not provision certificates or terminate
TLS itself.

```bash
MINTKEY_MCP_PUBLIC_URL=https://mcp.example.com
MINTKEY_PROXY_PUBLIC_URL=https://proxy.example.com
```

Caddy example fragment (illustrative):

```caddyfile
mcp.example.com {
    reverse_proxy localhost:8082
}

proxy.example.com {
    reverse_proxy localhost:8000
}
```

Mintkey does not require the URLs to share a host or port. They may be on
different domains, different ports, even different cloud accounts — only the
operator-facing values need to be set correctly.

## Egress (proxy → upstream APIs)

The proxy reaches upstream service APIs (`api.coingecko.com`, etc.) from inside
the docker network. If your network requires an HTTPS proxy or has firewall
rules, configure the Kong container's outbound proxy via the usual Kong
mechanisms. That is independent of `MINTKEY_PROXY_PUBLIC_URL`, which only
governs what agents see when they call IN to the proxy.

## Existing agent rows are NOT retroactively updated

`agent.mcp_endpoint` is snapshotted into the `agents` table at creation time.
Changing `MINTKEY_MCP_PUBLIC_URL` later does not rewrite old rows. New agents
created after the change use the new URL.

If you change the public URL and need old agents to reflect it, either:
- Revoke and re-create the affected agents, or
- Run a one-off `UPDATE agents SET mcp_endpoint = REPLACE(mcp_endpoint, ...)`
  SQL migration (no automation provided — pre-alpha).

## Legacy migration

If you previously deployed Mintkey with `MCP_BASE_URL`, `MINTKEY_MCP_URL`,
`MINTKEY_PROXY_URL`, or `KONG_PROXY_URL`, those still work. On startup, each
process logs once per legacy name:

```
WARN mintkey.public_url.legacy_env_var_used name=MCP_BASE_URL canonical=MINTKEY_MCP_PUBLIC_URL
```

To migrate cleanly:
1. Add the canonical names alongside the legacy ones.
2. Verify the bootstrap response (`curl http://<host>:8082/v1/tools/bootstrap`)
   reflects the same URLs.
3. Remove the legacy lines from `.env` and `docker-compose.yml`. Restart.

Legacy aliases will be removed in a future pre-alpha milestone with at least
one minor version of overlap.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Agent's first bootstrap call works, MCP calls fail with timeout | Bootstrap reflected old URL — agent created before `MINTKEY_MCP_PUBLIC_URL` was set. Re-create the agent. |
| `proxy_url` shows `localhost:8000` from a remote client | `MINTKEY_PROXY_PUBLIC_URL` not set on the admin-ui container, OR admin-ui not restarted after env change. |
| Dashboard MCP modal snippet shows localhost | `MINTKEY_MCP_PUBLIC_URL` not set on admin-ui, OR admin-ui pod predates the change. |
| Deprecation log spams every request | Bug — should be once per process. Open an issue. |
| Cross-machine call succeeds from `curl` but AI client fails | Check the client's MCP config has the public URL, not localhost. Re-copy from the dashboard. |

## See also

- [README.md](../README.md) — project overview
- [HOW-TO.md](HOW-TO.md) — end-to-end agent flows
- [docs/architecture/README.md](architecture/README.md) — service map
- [guides/github-quickstart.md](guides/github-quickstart.md) — first agent walkthrough
- [guides/hermes-coingecko-quickstart.md](guides/hermes-coingecko-quickstart.md) — CoinGecko agent walkthrough
- ADR-0017: [docs/architecture/01-architecture/adr/0017-round-3-corrections.md](architecture/01-architecture/adr/0017-round-3-corrections.md) — wire-form-everywhere (slug + agent ID semantics)
