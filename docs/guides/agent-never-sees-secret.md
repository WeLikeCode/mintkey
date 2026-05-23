# Agent Never Sees the Secret

This walkthrough proves Mintkey's core security property: an agent authenticates with a
Mintkey-issued API key (`mk_agent_*`), receives a short-lived brokered JWT, and calls a
backend through the egress proxy — but the real backend credential (e.g., a GitHub PAT,
an OpenAI API key) is **never returned to the agent**.

**Prerequisites:** `curl`, `jq` on `PATH`; Mintkey stack running (`make demo` or
`docker compose up -d`).

---

## 1. Setup

If you have not already started the stack, run:

```bash
make demo
```

This brings up all services and prints the admin URL (`http://localhost:8081`) and the
bootstrap admin password. After the stack is healthy, use the admin UI (or the
demo-mock-flow script) to create a service and an agent. The quickest path is the
automated script that sets everything up for you:

```bash
bash scripts/demo-mock-flow.sh --no-cleanup
```

The script prints the service ID and agent key (redacted). Capture them:

```bash
export MK_TENANT_ID="<tenant-id-printed-by-script>"   # e.g. tnt_01HXXXX
export MK_SVC_ID="<service-id-printed-by-script>"     # e.g. svc_01HXXXX
export MK_AGENT_KEY="mk_agent_YOUR_AGENT_KEY_HERE"     # copy from admin UI → Agents → key
```

To retrieve the tenant ID independently:

```bash
MK_TENANT_ID=$(curl -s http://localhost:8080/v1/tenants \
  -H "X-Platform-Admin: true" | jq -r '.data[0].id')
echo "Tenant: $MK_TENANT_ID"
```

To retrieve the service ID for the demo-mock-backend service:

```bash
MK_SVC_ID=$(curl -s "http://localhost:8080/v1/tenants/${MK_TENANT_ID}/services" \
  -H "X-Platform-Admin: true" | jq -r '.data[] | select(.slug=="demo-mock-backend") | .id')
echo "Service: $MK_SVC_ID"
```

---

## 2. Request a brokered JWT

The agent presents its Mintkey-issued key to the MCP server and receives a short-lived
JWT. The JWT is scoped to one service and one action.

```bash
TOKEN_RESP=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer ${MK_AGENT_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\":\"${MK_SVC_ID}\",\"action\":\"call\"}")

echo "$TOKEN_RESP" | jq .
```

Expected response shape:

```json
{
  "token": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...",
  "expires_at": "2026-05-19T12:01:00Z",
  "service_id": "svc_01HXXXX",
  "action": "call"
}
```

Capture the token:

```bash
BROKERED_JWT=$(echo "$TOKEN_RESP" | jq -r '.token')
```

**What the agent has at this point:** a JWT signed by Mintkey's broker. Inspect its
payload — it contains the service ID, action, agent ID, and expiry. It does **not**
contain any backend credential:

```bash
# Decode the JWT payload (base64url — no secret required)
echo "$BROKERED_JWT" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null | jq .
```

You will see fields like `sub` (agent ID), `svc` (service ID), `act` (action), and `exp`
(expiry). No `credential`, no PAT, no backend API key.

---

## 3. Proxy call

The agent uses the brokered JWT as a Bearer token on the proxy. Kong routes the request
to the proxy-plugin, which validates the JWT, looks up the real credential from the vault
adapter, and **injects** it into the upstream request before forwarding.

```bash
PROXY_RESP=$(curl -s -X POST \
  "http://localhost:8000/v1/call/${MK_SVC_ID}/echo" \
  -H "Authorization: Bearer ${BROKERED_JWT}" \
  -H "Content-Type: application/json" \
  -d '{"hello":"mintkey-walkthrough"}')

echo "$PROXY_RESP" | jq .
```

Expected response (mock-backend echo mode):

```json
{
  "method": "POST",
  "path": "/echo",
  "headers": {
    "x-api-key": "canary-demo-api-key",
    "content-type": "application/json"
  },
  "body": {"hello": "mintkey-walkthrough"}
}
```

The `x-api-key` header in the echo response shows what the **backend** received. This is
the real credential that Mintkey injected. The agent never sent this header — it only
sent the brokered JWT:

```bash
# Confirm: the agent sent no x-api-key header
# The JWT authorization header is what the agent sent:
echo "Agent sent: Authorization: Bearer $(echo "$BROKERED_JWT" | cut -c1-20)..."
echo "Backend received: x-api-key=$(echo "$PROXY_RESP" | jq -r '.headers["x-api-key"]')"
```

The two values are entirely different. The backend credential (`canary-demo-api-key`)
existed only inside the proxy's request scope.

---

## 4. Audit log check

Every proxied call emits an audit event. The audit log records the call but **never**
stores the upstream credential value.

```bash
curl -s "http://localhost:8080/v1/tenants/${MK_TENANT_ID}/audit" \
  -H "X-Platform-Admin: true" | jq '.data[0]'
```

Expected audit event shape:

```json
{
  "id": "evt_01HXXXX",
  "event_type": "token.used",
  "actor_id": "agt_01HXXXX",
  "resource_type": "service",
  "resource_id": "svc_01HXXXX",
  "action": "call",
  "timestamp": "2026-05-19T12:00:30Z",
  "metadata": {
    "service_slug": "demo-mock-backend",
    "path": "/echo"
  }
}
```

Note the absence of `credential_value`, `api_key`, `token_value`, or any field
containing the real backend secret. The audit event is append-only and hash-chained
(SHA-256 per ADR-0014.7); you can verify chain integrity with:

```bash
curl -s -X POST http://localhost:8080/v1/admin/audit/verify-chain \
  -H "X-Platform-Admin: true" \
  -H "Content-Type: application/json" \
  -d "{\"tenant_id\": \"${MK_TENANT_ID}\"}" | jq .
```

A `{"valid": true}` response confirms no audit event has been tampered with.

---

## 5. OTel trace check

Every request carries a W3C `traceparent` header and is exported to Jaeger. Open the
Jaeger UI and confirm the credential is absent from all span attributes.

Open: [http://localhost:16686](http://localhost:16686)

Steps:
1. Select service **mcp-server** from the dropdown.
2. Find the trace corresponding to your `request_token` call (the timestamp matches the
   `expires_at` minus 60 seconds).
3. Expand all spans.
4. Use Cmd+F (or browser search) to search for `credential`, `api_key`, `x-api-key`, or
   `canary`. You will find zero matches.

To extract the trace ID from the proxy response header:

```bash
curl -s -I -X POST \
  "http://localhost:8000/v1/call/${MK_SVC_ID}/echo" \
  -H "Authorization: Bearer ${BROKERED_JWT}" \
  -H "Content-Type: application/json" \
  -d '{}' | grep -i traceparent
```

Then paste the trace ID into Jaeger → **Search** → **Trace ID** field.

The span attribute allowlist for security-sensitive fields is enforced by the OTel
collector config (`infra/observability/otel-collector-config.yaml`); any span attribute whose key matches
`*credential*`, `*secret*`, or `*api_key*` is filtered out before export.

---

## 6. Conclusion

At the end of this walkthrough, the call chain was:

```
Agent
  │  holds:  mk_agent_YOUR_AGENT_KEY_HERE   (Mintkey-issued, revocable)
  │
  ▼  POST /v1/tools/request_token  ──────────────────►  mcp-server / broker
                                                         issues short-lived JWT
  │  holds:  eyJhbGci... (JWT, 60-second TTL)
  │
  ▼  POST /v1/call/<svc_id>/echo  (Bearer JWT)  ──────►  Kong → proxy-plugin
                                                         validates JWT
                                                         fetches real credential
                                                         from vault-adapter
                                                         injects x-api-key header
  │  response:  echo of upstream request
  │             (agent sees the echo, not the raw credential)
  ▼
  Done
```

**Key facts:**

- The agent held `mk_agent_YOUR_AGENT_KEY_HERE` — a Mintkey-issued API key, not the
  real backend credential.
- The backend received `canary-demo-api-key` (or your real PAT in production) — injected
  by the proxy, never visible to the agent.
- The audit log records the call event with no credential value.
- The OTel trace contains no secret spans or attributes.
- The brokered JWT expired 60 seconds after issuance (ADR-0006) and cannot be reused.

This is Mintkey's core security guarantee: **the agent never sees the real credential.**

---

## Related guides

- [`docs/guides/github-quickstart.md`](github-quickstart.md) — end-to-end quickstart
  with a real GitHub PAT.
- [`docs/guides/10min-mock-demo.md`](10min-mock-demo.md) — PAT-free mock demo flow.
- [`docs/DEBUG.md`](../DEBUG.md) — troubleshooting common failure modes.
- [`examples/python-agent-snippet/`](../../examples/python-agent-snippet/) — Python
  code demonstrating the same flow.
- [`examples/typescript-agent-snippet/`](../../examples/typescript-agent-snippet/) —
  TypeScript equivalent.
