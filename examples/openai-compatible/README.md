# OpenAI-compatible API example

Mintkey can broker access to any HTTPS service, including OpenAI-compatible endpoints.
This example shows how to register an OpenAI-compatible service (or any HTTP API that
accepts Bearer-token authentication) in Mintkey, grant an agent access to it, and then
use the standard `openai` Python SDK to call it — with Mintkey transparently injecting
the real API key on every request.

**The agent never holds the real OpenAI API key.** It holds only a brokered JWT issued
by Mintkey's broker. The proxy strips that JWT, looks up the stored OpenAI key from the
vault adapter, and injects `Authorization: Bearer <real-key>` before forwarding to the
upstream endpoint.

For the demo, the service is the local `mock-backend` in echo mode — no real OpenAI key
is required.

---

## How it works

```
openai SDK
   │   api_key=<brokered-JWT>
   │   base_url=http://localhost:8000/v1/call/<svc_id>
   │
   ▼  POST /v1/call/<svc_id>/v1/chat/completions
Kong → proxy-plugin
   │   validates JWT
   │   fetches real credential from vault-adapter
   │   injects: Authorization: Bearer <real-openai-key>
   ▼  forwards to upstream (e.g., https://api.openai.com or mock-backend)
```

The OpenAI SDK requires an `api_key` parameter. The trick: set `api_key` to the
**brokered JWT** obtained from the Mintkey MCP server. The proxy strips it and replaces
it with the real key before the request leaves Mintkey's network.

---

## Prerequisites

- Mintkey stack running: `make demo` (or `docker compose up -d`)
- `curl` and `jq` on `PATH`
- Python 3.10+ with `pip install openai httpx`
- Operator access to run `register-service.sh` (admin credentials)

---

## Step 1: Register the OpenAI-compatible service

Run the registration script once as an operator. It creates the service entry,
stores the credential, and grants the demo agent access.

```bash
bash examples/openai-compatible/register-service.sh
```

The script is idempotent: if the service slug already exists it skips creation.
It prints the resulting `SVC_ID` — export it for step 2.

For production, replace the mock-backend URL and credential with real values
(e.g., `https://api.openai.com` and your actual OpenAI API key stored via admin UI).

---

## Step 2: Run the agent

```bash
export MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE
export MINTKEY_SVC_ID=svc_01HXXXX   # printed by register-service.sh

python3 examples/openai-compatible/agent.py
```

The agent:
1. Requests a brokered JWT from the MCP server (using `MINTKEY_AGENT_KEY`).
2. Passes that JWT as the `api_key` to the OpenAI SDK, with `base_url` pointing to
   the Mintkey proxy.
3. Calls `chat.completions.create(...)` — the SDK sends a normal OpenAI-compatible
   request; the proxy injects the real credential.
4. Prints a redacted response summary.

---

## Extending to real OpenAI

To broker access to the real OpenAI API:

1. In admin UI → **Services → New Service**:
   - `base_url`: `https://api.openai.com`
   - `auth_scheme`: `bearer_token`
2. In admin UI → **Services → (service) → Credentials → Add**:
   - Store your real `sk-proj-...` OpenAI API key.
3. Grant your agent `call` permission on this service.
4. In `agent.py`, set `base_url` to `http://localhost:8000/v1/call/<svc_id>` and
   `api_key` to the brokered JWT.

The OpenAI SDK transparently proxies through Mintkey. Your agent code never touches
the real `sk-proj-*` key.

---

## Files

| File | Purpose |
|---|---|
| `register-service.sh` | One-time operator setup: create service + credential + agent grant |
| `agent.py` | Agent code using the OpenAI SDK through the Mintkey proxy |
| `README.md` | This file |
