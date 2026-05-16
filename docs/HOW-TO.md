# How-To: Mintkey operator playbook

The substantive runbooks live under [`docs/guides/`](guides/). This file is the index. Each
section below names the task and links out to the guide that covers it; content is not duplicated
here.

---

## 1. Prerequisites

Do not repeat the full table here — see [`QUICKSTART.md`](../QUICKSTART.md) "Prerequisites"
section for the exact list (Docker, docker compose, ports, disk space).

---

## 2. First-time setup

| Step | One-line summary | Full instructions |
|---|---|---|
| 1. Bring the stack up | `docker compose up -d` — 15 long-running containers + 2 one-shot jobs | [`QUICKSTART.md`](../QUICKSTART.md) §1 |
| 2. Get the bootstrap admin password | Printed once to stdout; also at `./data/bootstrap-secrets/` (mode `0400`) | [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) §0 |
| 3. Open the Admin UI | `http://localhost:8081` | [`PORTS.md`](../PORTS.md) "Quick access" |

---

## 3. Service playbooks

| Task | Guide |
|---|---|
| Register a GitHub service (PAT, API key) | [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) |
| Register a CoinGecko service via Hermes | [`docs/guides/hermes-coingecko-quickstart.md`](guides/hermes-coingecko-quickstart.md) |
| Add a new auth scheme (developer task) | [`CONTRIBUTING.md`](../CONTRIBUTING.md) §6; [`CLAUDE.md`](../CLAUDE.md) "How to add an X" |

---

## 4. Operations

The proxy endpoint for all brokered calls is **`http://localhost:8000`** (env `MINTKEY_PROXY_URL`,
per [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) lines 358–360 and the Ports
reference at lines 414–428). Do not use port `8087` — that is the vault-adapter HTTP port, not the
proxy.

If clients on other machines need to reach this Mintkey instance, set `MINTKEY_MCP_PUBLIC_URL` and
`MINTKEY_PROXY_PUBLIC_URL` — see [NETWORK.md](NETWORK.md).

| Task | Where to look |
|---|---|
| Rotate a credential | [`QUICKSTART.md`](../QUICKSTART.md) §8 and [`docs/architecture/03-flows/F-OP-03-register-credential-and-test.md`](architecture/03-flows/F-OP-03-register-credential-and-test.md) |
| Revoke an agent | [`docs/architecture/03-flows/F-OP-04-create-agent-and-permissions.md`](architecture/03-flows/F-OP-04-create-agent-and-permissions.md) |
| Inspect the audit log | `POST /v1/admin/audit/verify-chain` — see [`QUICKSTART.md`](../QUICKSTART.md) §9 "Troubleshooting" (note: requires `PlatformAdmin` role; pass `Authorization: Bearer <operator-session-token>`) |
| Read traces | `http://localhost:16686` (Jaeger) — see [`PORTS.md`](../PORTS.md) |
| Read dashboards | `http://localhost:3003` (Grafana) — see [`PORTS.md`](../PORTS.md) |
| Reset Grafana password | [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) §9 |

---

## 5. Database schema changes

Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) first. The schema is owned by Liquibase per
[ADR-0015](architecture/01-architecture/adr/0015-liquibase-schema-source-of-truth.md); never edit
SQLAlchemy directly. If you are an operator and the change is to your deployment's schema, you
still go through Liquibase changelogs — add a new changeset, never edit an existing one.

---

## 6. Stack health checks

| Command | Expected outcome |
|---|---|
| `docker compose ps` | All 15 long-running services show `Up (healthy)`; `liquibase` and `seed-job` show `Exit 0` |
| `curl http://localhost:8080/v1/ready` | `200 OK` with `{"status": "ok"}` (reports failing dependencies on `503`) |
| `make test-arch` | Architecture invariants: RLS coverage, OpenAPI parity, SQLAlchemy mirror diff — all exit `0` |
| `make smoke` | E2E-01 happy path; completes in ≤ 90 s |
| `docker compose logs --tail=50 <svc>` | Recent logs for any service; replace `<svc>` with e.g. `mintkey-admin-api-1` |

---

## Connect a vanilla MCP client to Mintkey

To wire Claude Code (or Cursor, mcp-cli, etc.) at Mintkey:

1. Get an agent API key. In the admin UI (`http://<host>:8081`), create an Agent + grant it permission on one or more Services. The key is shown once — copy `mk_agent_<...>`.

2. Configure your MCP client. Point the server URL at:
   ```
   http://<MINTKEY_MCP_PUBLIC_URL>/mcp
   ```
   (For local dev: `http://localhost:8082/mcp`. For LAN: `http://10.243.1.200:8082/mcp`.)

3. Set the Authorization header to `Bearer mk_agent_<your-key>`.

4. The client will call `initialize` (unauthenticated), then `tools/list` and `tools/call` (authenticated). The six Mintkey tools (`mintkey_bootstrap`, `mintkey_list_services`, `mintkey_discover`, `mintkey_describe_service`, `mintkey_get_openapi`, `mintkey_request_token`) become available to the LLM.

5. Verify with curl:
   ```bash
   # Handshake (no auth needed)
   curl -X POST http://<host>:8082/mcp \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}'

   # List available tools (auth required)
   curl -X POST http://<host>:8082/mcp \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer mk_agent_<your-key>' \
     -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
   ```

For the full agent onboarding markdown (which the `initialize` response also points at), GET `http://<host>:8082/v1/tools/bootstrap`.

See [AUTH.md](AUTH.md) for the full header reference and [NETWORK.md](NETWORK.md) for the discovery endpoint table.

---

## 7. Where else to look

| Need | Document |
|---|---|
| Layered troubleshooting (triage tree, per-service failure modes) | [`docs/DEBUG.md`](DEBUG.md) |
| Report a bug or file a feature request | [`docs/REPORTING.md`](REPORTING.md) |
| Report a security vulnerability | [`SECURITY.md`](../SECURITY.md) |
