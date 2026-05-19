# Python agent snippet

A minimal Python script demonstrating how an agent authenticates with Mintkey,
requests a short-lived brokered JWT, and calls a backend service through the
Mintkey egress proxy — without ever holding the real backend credential.

## Prerequisites

- Mintkey stack running: `make demo` (or `docker compose up -d`)
- A registered service with a credential stored (use admin UI or `bash scripts/demo-mock-flow.sh --no-cleanup`)
- An agent created with a `call` permission grant on that service
- Python 3.10+

## Setup

```bash
cd examples/python-agent-snippet
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
export MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE
export MINTKEY_SVC_ID=svc_01HXXXX   # shown in admin UI → Services

python3 agent.py
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
    HTTP status    : 200
    Agent sent     : Authorization: Bearer eyJhbGciOi...
    Backend received x-api-key: <REDACTED>
    Echo body      : {'hello': 'mintkey-python-snippet'}

SUCCESS — the agent held only a short-lived JWT;
          the real credential was injected by the Mintkey proxy.
```

The `x-api-key` value sent to the backend is redacted in this output. The agent
never had access to it — only the Mintkey proxy injected it into the upstream request.

## What this demonstrates

| Step | What happens | Agent sees |
|---|---|---|
| `request_token` | MCP server validates agent key; broker issues JWT | JWT only (no backend cred) |
| Proxy call | Kong → proxy-plugin validates JWT; vault-adapter returns real cred; proxy injects it upstream | Echo response (not the raw cred) |

See [`docs/guides/agent-never-sees-secret.md`](../../docs/guides/agent-never-sees-secret.md)
for a detailed walkthrough with audit log and OTel trace verification.
