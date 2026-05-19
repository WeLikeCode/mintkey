# TypeScript agent snippet

A minimal TypeScript script demonstrating how an agent authenticates with Mintkey,
requests a short-lived brokered JWT, and calls a backend service through the Mintkey
egress proxy — without ever holding the real backend credential.

Uses the native `fetch` API (Node 18+); no extra HTTP client dependency.

## Prerequisites

- Node 18+
- pnpm (or npm)
- Mintkey stack running: `make demo` (or `docker compose up -d`)
- A registered service with a credential stored (use admin UI or `bash scripts/demo-mock-flow.sh --no-cleanup`)
- An agent created with a `call` permission grant on that service

## Setup

```bash
cd examples/typescript-agent-snippet
pnpm install   # or npm install
```

## Run

```bash
export MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE
export MINTKEY_SVC_ID=svc_01HXXXX   # shown in admin UI → Services

pnpm start
```

Using npm:

```bash
npm start
```

Optional overrides (default to `localhost`):

```bash
export MINTKEY_MCP_URL=http://localhost:8082
export MINTKEY_PROXY_URL=http://localhost:8000
```

## Expected output

```
[1] Requesting brokered JWT from http://localhost:8082/v1/tools/request_token ...
    JWT received: eyJhbGciOi...  expires_at=2026-05-19T12:01:00Z
    (real backend credential NOT present in this response)

[2] Calling backend through proxy: POST http://localhost:8000/v1/call/svc_01HXXXX/echo ...

[3] Result summary:
    Agent sent     : Authorization: Bearer eyJhbGciOi...
    Backend received x-api-key: <REDACTED>
    Echo body      : {"hello":"mintkey-typescript-snippet"}

SUCCESS — the agent held only a short-lived JWT;
          the real credential was injected by the Mintkey proxy.
```

## What this demonstrates

| Step | What happens | Agent sees |
|---|---|---|
| `request_token` | MCP server validates agent key; broker issues JWT | JWT only (no backend cred) |
| Proxy call | Kong → proxy-plugin validates JWT; vault-adapter returns real cred; proxy injects it upstream | Echo response (not the raw cred) |

See [`docs/guides/agent-never-sees-secret.md`](../../docs/guides/agent-never-sees-secret.md)
for a detailed walkthrough with audit log and OTel trace verification.
