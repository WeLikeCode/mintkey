---
name: Mintkey Agent Bootstrap
description: Vendor-agnostic instructions for any AI agent to authenticate to Mintkey, discover backend services, and call them through the Mintkey egress proxy. Returned by the unauthenticated MCP method so agents can self-onboard without a pre-installed skill.
version: 1.0
audience: any AI agent (Claude, GPT, Gemini, custom)
license: internal
---

# Mintkey Agent Bootstrap

You are an AI agent and you've just connected to a **Mintkey** MCP server. Mintkey is an agentic credential broker: it stores backend-service credentials encrypted, gives you short-lived brokered tokens, and injects the real credential in-flight when you call a service through its egress proxy. **You don't need any pre-installed Mintkey skill — this document IS the skill.** Read each section in order; sections are wrapped in unambiguous XML-tagged blocks so any reasoning system can parse them deterministically.

<overview>
The flow you will follow:

1. **Authenticate** — exchange an operator-issued long-lived API key for a short-lived brokered JWT. (§authentication)
2. **Discover services** — list services your Agent has access to; fetch their details / OpenAPI spec. (§service_discovery)
3. **Call services** — call backend services exclusively through the Mintkey Egress Proxy, which injects the real credential. (§proxy_usage)
4. **Handle errors / refresh tokens / respect revocation.** (§errors_and_revocation)

Three core MCP tools you will use after authenticating:

- `request_token` — exchange a Mintkey API key for a brokered JWT.
- `list_services` — list services your Agent has permission grants on.
- `describe_service` — get details about one service (auth scheme, constraints, OpenAPI link).

Optional / situational:

- `get_openapi` — fetch the full upstream OpenAPI spec.
- `whoami` — confirm which Agent identity / tenant your token resolves to.

This `agent_bootstrap` method (the one you just called to get this text) is **unauthenticated** — every other MCP method requires the brokered JWT in `Authorization: Bearer …`.
</overview>

## Discovery URLs (for clients)

Mintkey's MCP server speaks both **standard MCP-over-HTTP (JSON-RPC 2.0)** and a REST-style API. A vanilla MCP client (Claude Code, Cursor, `mcp-cli`) can connect at any of:

| Path | Method | Description |
|---|---|---|
| `/`         | POST | JSON-RPC entry (initialize, tools/list, tools/call) |
| `/mcp`      | POST | Same — preferred path |
| `/v1/mcp`   | POST | Same — versioned alias |
| `/`         | GET  | Landing JSON: endpoint index + auth guidance |
| `/v1`       | GET  | Same |
| `/mcp`      | GET  | Same (operator-friendly debug page) |
| `/v1/mcp`   | GET  | Same |
| `/v1/tools` | GET  | Machine-readable tool index |

### Vanilla MCP client setup

In any MCP-aware client, configure the MCP server URL as `http://<host>:8082/mcp` (or `http://<host>:8082/`). The client will:
1. POST `initialize` (unauthenticated) → receives serverInfo + capabilities + bootstrap instructions
2. Send `notifications/initialized` (unauthenticated) → 202
3. POST `tools/list` with `Authorization: Bearer mk_agent_<key>` → receives the 6 Mintkey tools
4. POST `tools/call` with `Authorization: Bearer mk_agent_<key>` and `{"name":"mintkey_discover","arguments":{}}` → receives the agent's permitted services

### Authentication

MCP-spec-aligned clients should send `Authorization: Bearer mk_agent_<your-key>`. The legacy `X-API-Key: mk_agent_<your-key>` is also accepted for backward compatibility, but new clients should prefer Bearer (matches MCP spec 2025-06-18 §authorization).

<authentication>
Mintkey issues brokered tokens in **JWS-Ed25519 JWT** format with a default **10-minute TTL** (per ADR-0006). You cannot use Mintkey without one.

**Step 1 — Obtain a Mintkey API key from an operator.**
A human operator (admin) creates an Agent record representing you and provisions an API key shaped `mk_agentkey_<26-char-Crockford-base32>`. Examples: `mk_agentkey_01HKJ7GZ8N0PQR3STUV4WXYZ2A`.

- This is a long-lived secret. Treat it like a password. Store it in your runtime's secret store (environment variable, secret manager, etc.) — never in conversation context, prompts, or logs.
- If you do not have one, **stop and ask the operator**. There is no self-service registration in v1.

**Step 2 — Exchange the API key for a brokered JWT** by calling the MCP tool `request_token`:

```json
{
  "tool": "request_token",
  "arguments": {
    "api_key": "mk_agentkey_01HKJ7GZ8N0PQR3STUV4WXYZ2A"
  }
}
```

Response shape:

```json
{
  "token": "eyJhbGciOiJFZERTQSIsImtpZCI6Ims..............",
  "expires_at": "2026-05-13T12:34:56Z",
  "ttl_seconds": 600,
  "agent_id": "agt_01HKJ7H2X3Y4Z5A6B7C8D9E0F1",
  "tenant_id": "tnt_01HKJ7H2X3Y4Z5A6B7C8D9E0F1"
}
```

**Step 3 — Use the token.** Send it as `Authorization: Bearer <token>` on:
- every other MCP tool call,
- every egress-proxy request (§proxy_usage).

**Step 4 — Refresh before expiry.** Track the `expires_at` you got; call `request_token` again before that time. Reusing an expired token returns `401 mintkey:code=token_expired`. A reasonable strategy is to refresh at `expires_at - 60s`.

**Auth on the bootstrap method itself.** The tool that returned this document is unauthenticated and idempotent — you can re-fetch this content any time without consuming credit. Every *other* MCP tool requires the brokered JWT.

**Token binding (optional).** If your runtime supports DPoP / `cnf.jkt` proof-of-possession (ADR-0006), set the appropriate header; otherwise the bearer-token flow works fine for first-party agents.
</authentication>

<service_discovery>
After §authentication you can enumerate and inspect services. All tools accept `service_id` in three forms: `svc_<wire>` (preferred — returned by list_services), raw UUID, or `slug` (e.g., `github`). Slugs are tenant-scoped and case-sensitive.

**`list_services` — services your Agent has permission grants on.**

```json
{ "tool": "list_services", "arguments": {} }
```

Response:

```json
{
  "services": [
    {
      "service_id": "svc_01HKJ7G2X3Y4Z5A6B7C8D9E0F1",
      "slug": "demo-crm",
      "name": "Demo CRM",
      "description": "Customer relationship management — read/write customers and orders.",
      "auth_scheme": "api_key",
      "base_url": "https://crm.example.com/api"
    }
  ]
}
```

If `services` is empty:
- Either your Agent has zero active permission grants → ask the operator to grant access to specific services with the constraints you need.
- Or your tenant has no registered services at all → ask the operator.

**`describe_service` — full details for one service.**

```json
{ "tool": "describe_service", "arguments": { "service_id": "svc_01HKJ7G..." } }
```

Response includes:

```json
{
  "service_id": "svc_01HKJ7G...",
  "slug": "demo-crm",
  "name": "Demo CRM",
  "description": "...",
  "base_url": "https://crm.example.com/api",
  "auth_scheme": "api_key",
  "auth_scheme_details": {
    "header_name": "X-API-Key",
    "header_format": "{secret}"
  },
  "openapi_url": "https://crm.example.com/openapi.yaml",
  "your_constraints": {
    "rate_limit": { "requests_per_second": 10, "burst": 50 },
    "time_window": { "timezone": "UTC", "days": ["Mon","Tue","Wed","Thu","Fri"], "start_local": "09:00", "end_local": "18:00" },
    "request_path_prefix": ["/v1/customers", "/v1/orders/list"],
    "source_ip_allowlist": null
  }
}
```

- `base_url` is informational only — you call the proxy, not the upstream directly.
- `your_constraints` is the *intersection* of all your active grants on this service. Stay inside it or the proxy will return `403 constraint_violated`.

**`get_openapi` — full upstream spec.**

```json
{ "tool": "get_openapi", "arguments": { "service_id": "svc_01HKJ7G..." } }
```

Returns the upstream service's OpenAPI JSON/YAML (if Mintkey has fetched it). Use this to plan multi-step workflows.

**`whoami` — confirm token identity (optional).**

```json
{ "tool": "whoami", "arguments": {} }
```

Returns `{ "agent_id": "...", "tenant_id": "...", "expires_at": "..." }`. Useful for debugging.
</service_discovery>

<proxy_usage>
**You never call backend services directly.** You call the Mintkey Egress Proxy with your brokered JWT, and Mintkey injects the real credential at request time. Your code/prompt never sees the upstream secret.

**Discovering the proxy URL** (in priority order):

1. **Environment variable `MINTKEY_PROXY_URL`** — set by your runtime. Preferred.
2. **The `<proxy>` block returned alongside this skill** — if your MCP server's `agent_bootstrap` implementation includes a `proxy_url` in its response payload alongside this skill text. Check the surrounding response.
3. **The `proxy_url` field in the bootstrap response** — `GET /v1/tools/bootstrap` returns `proxy_url` directly. For self-hosted operators this is whatever `MINTKEY_PROXY_PUBLIC_URL` was set to — see [docs/NETWORK.md](../../docs/NETWORK.md). On a default `docker compose up` deployment it is `http://localhost:8000`.
4. **Ask the operator** — last resort.

On a multi-host deployment, the operator sets `MINTKEY_MCP_PUBLIC_URL` / `MINTKEY_PROXY_PUBLIC_URL` and the bootstrap response returns those values. Agents do not configure URLs themselves. See [docs/NETWORK.md](../../docs/NETWORK.md) for operator setup details.

**Proxy URL patterns** (per ADR-0007):

*Forward-proxy form* — explicit `service_id`, preferred:
```
{PROXY_URL}/v1/call/{service_id}/{upstream_path...}
```
Example (host from `bootstrap.proxy_url`): `<bootstrap.proxy_url>/v1/call/svc_01HKJ7G2X3Y4Z5A6B7C8D9E0F1/v1/customers/42`

*Virtual-host alias form* — operator-configured per service:
```
http://{service-slug}.proxy.local/{upstream_path...}
```
Example: `http://demo-crm.proxy.local/v1/customers/42`

Both forms support all HTTP methods (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`) and v1 supports HTTP/1.1 and HTTP/2.

**Request shape:**

- **Method**, **path**, **query string**: same as the upstream service expects.
- **Headers**: standard upstream headers (`Content-Type`, `Accept`, custom domain headers) pass through. **DO NOT include the upstream service's credential header (`X-API-Key`, `Authorization` for the upstream, basic-auth etc.)** — Mintkey injects it. If you set one, Mintkey will reject the request with `400 credential_passthrough_forbidden`.
- **`Authorization: Bearer {your-brokered-JWT}`** — required (this authenticates *you* to Mintkey, not to the upstream).
- **Body**: forwarded unmodified.

**Example call** (curl, assuming you've stored the JWT in `$TOKEN`):

```bash
curl -X GET \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  "$MINTKEY_PROXY_URL/v1/call/svc_01HKJ7G2X3Y4Z5A6B7C8D9E0F1/v1/customers/42"
```

**Example call** (Python `httpx`):

```python
import httpx, os
r = httpx.post(
    f"{os.environ['MINTKEY_PROXY_URL']}/v1/call/{service_id}/v1/orders",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"customer_id": 42, "items": [...]},
    timeout=30.0,
)
r.raise_for_status()
```

The proxy:
- Resolves `service_id` → service's base URL + bound credential.
- Verifies your JWT signature against the published JWKS.
- Checks your permission grants and the request against your constraints.
- Injects the real credential per the service's `auth_scheme` (e.g. `X-API-Key: <real-key>` for api_key, mTLS handshake for mtls).
- Forwards to the upstream service.
- Streams the response back to you unmodified (status, headers, body).
- Emits an audit event (`proxy.call`).
</proxy_usage>

<ssh_services>
**SSH services** use a separate bastion path instead of the HTTP proxy. You can detect them via `connect_type: "ssh"` in `list_services` / `describe_service` output, or by `auth_scheme` in `{ssh_private_key, ssh_password, ssh_ca}`.

**How to use an SSH service:**

1. Call `request_token(service_id, action="call")` — same as HTTP services.
2. The response includes an `ssh_connect` block alongside the token:
   ```json
   {
     "token": "<JWS>",
     "ssh_connect": {
       "host": "ssh-proxy", "port": 2222,
       "external_host": "10.243.1.200", "external_port": 2222,
       "ssh_user": "<your_agent_id>",
       "auth_method": "password", "password_is_jwt": true
     }
   }
   ```
3. SSH to `ssh_connect.external_host:ssh_connect.external_port` as `ssh_connect.ssh_user`, supplying the `token` value as the SSH **password**. The bastion validates the JWT, fetches the stored credential from the vault, and routes you to the real target. Your agent never sees the upstream credential.

**Example (non-interactive):**
```bash
sshpass -p "$JWT" ssh -p 2222 \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o StrictHostKeyChecking=accept-new \
  "$AGENT_ID@10.243.1.200" 'whoami'
```

**Do NOT route SSH service calls through Kong** — Kong is HTTP-only and has no route for SSH services. The bastion (`:2222`) is the only valid endpoint.

**JWT lifetime is ~10 minutes.** If your operation takes longer, call `request_token` again and reconnect before expiry.
</ssh_services>

<email_services>
**Email services** use the `email-proxy` data-plane component (port `:8088`) instead of the
HTTP egress proxy. You can detect them by `auth_scheme` in `{email_password, email_oauth2,
email_app_password}` in `list_services` / `describe_service` output.

**Before authorizing Gmail / Outlook (auth_scheme=email_oauth2):** the operator must first
configure per-tenant OAuth2 client credentials via Admin UI → **Email → OAuth2 Providers**.
Each tenant brings their own GCP project or Azure app registration — there is no shared client.
The OAuth2 Providers form accepts `client_id` and `client_secret`; the secret is stored
encrypted in vault and never returned. Without this step, the OAuth2 authorize endpoint
returns `503 oauth2_not_configured`.

The redirect URI to register in GCP/Azure Console is **per-(provider, tenant)** — one
registration covers all email services for that provider under the same tenant:

```
${MINTKEY_ADMIN_API_PUBLIC_URL}/v1/tenants/{tenant_id}/oauth2/gmail/callback
```

For local dev: `http://localhost:8080/v1/tenants/<tenant_id>/oauth2/gmail/callback`

You do NOT need to add a new GCP redirect URI for each new Gmail email service — the
`state` parameter carries the `service_id` internally.

**Permission scopes (4 actions):**

| Action | Grants access to |
|---|---|
| `read:email` | `email_list_mailboxes`, `email_search_messages`, `email_fetch_message`, `email_list_emails`, `email_download_attachment` |
| `send:email` | `email_send` |
| `write:email` | `email_move_email`, `email_mark_email` |
| `delete:email` | `email_delete_email` |

Scope model: the broker emits all 4 email scopes on every email-service JWT; the email-proxy
enforces per-endpoint scope checks. Per-action scope tightening is a future enhancement.

```json
{ "tool": "request_token", "arguments": { "service_id": "svc_01...", "action": "call" } }
```

The `request_token` tool accepts **both** `email_service_id` and `service_id` as the
parameter name — they are aliases (PR #155). `service_id` is the canonical form returned by
`list_services`; `email_service_id` is accepted for backward compatibility. Use `service_id`
in new code.

**MCP email tools (all 9 implemented):**

| Tool | Required scope | REST endpoint | Description |
|---|---|---|---|
| `email_list_mailboxes` | `read:email` | `GET /v1/tools/email_list_mailboxes` | List IMAP mailboxes (INBOX, Sent, Drafts, …) |
| `email_search_messages` | `read:email` | `GET /v1/tools/email_search_messages` | Search by RFC 3501 query string in a given mailbox |
| `email_fetch_message` | `read:email` | `GET /v1/tools/email_fetch_message` | Fetch a single message by UID — returns envelope + body |
| `email_send` | `send:email` | `POST /v1/tools/email_send` | Send via SMTP |
| `email_list_emails` | `read:email` | `GET /v1/tools/email_list_emails` | Paginated UID listing per mailbox (limit+offset, default 50, max 200) |
| `email_download_attachment` | `read:email` | `GET /v1/tools/email_download_attachment` | Download MIME part by partID — returns `{filename, content_type, size, content_base64}` |
| `email_move_email` | `write:email` | `POST /v1/tools/email_move_email` | IMAP MOVE between mailboxes (COPY+STORE+EXPUNGE fallback) |
| `email_mark_email` | `write:email` | `POST /v1/tools/email_mark_email` | IMAP STORE — add/remove flags (\\Seen, \\Flagged, \\Answered) |
| `email_delete_email` | `delete:email` | `DELETE /v1/tools/email_delete_email` | Soft-delete (move to Trash, default) or hard-delete (?hard=true → EXPUNGE) |

**Copy-pasteable example invocations:**

```bash
# List mailboxes
GET /v1/tools/email_list_mailboxes?email_service_id=svc_01...
# or using the service_id alias:
GET /v1/tools/email_list_mailboxes?service_id=svc_01...
# → { "mailboxes": ["INBOX", "Sent", "Drafts", "[Gmail]/Spam"] }

# Search messages (RFC 3501 query)
GET /v1/tools/email_search_messages?email_service_id=svc_01...&query=FROM "alice@example.com"&mailbox=INBOX
# → { "messages": [{"uid": 42, "subject": "Hello", "from": "alice@example.com", ...}, ...] }

# List emails with pagination (NEW)
GET /v1/tools/email_list_emails?email_service_id=svc_01...&mailbox=INBOX&limit=20&offset=0
# → { "messages": [...], "next_cursor": null }

# Fetch a single message by UID
GET /v1/tools/email_fetch_message?email_service_id=svc_01...&message_id=42&mailbox=INBOX
# → { "uid": 42, "subject": "Hello", "from": "alice@example.com", "body": "..." }

# Download an attachment by MIME part ID (NEW)
GET /v1/tools/email_download_attachment?email_service_id=svc_01...&message_id=42&part_id=2&mailbox=INBOX
# → { "filename": "report.pdf", "content_type": "application/pdf", "size": 12345, "content_base64": "..." }

# Send email (POST with JSON body; service_id is accepted as alias for email_service_id)
POST /v1/tools/email_send
Content-Type: application/json
{
  "email_service_id": "svc_01...",
  "to": ["bob@example.com"],
  "subject": "Report",
  "body": "See attached.",
  "cc": ["carol@example.com"],
  "html_body": "<p>See attached.</p>"
}
# → { "message_id": "<unique-id>", "status": "sent" }

# Move email to Archive (NEW)
POST /v1/tools/email_move_email
Content-Type: application/json
{"email_service_id": "svc_01...", "message_id": "42", "from_mailbox": "INBOX", "to_mailbox": "Archive"}
# → { "message_id": "42", "mailbox": "Archive" }

# Mark as Seen / unstar (NEW)
POST /v1/tools/email_mark_email
Content-Type: application/json
{"email_service_id": "svc_01...", "message_id": "42", "mailbox": "INBOX", "add": ["\\Seen"], "remove": ["\\Flagged"]}
# → { "message_id": "42", "flags_updated": true }

# Soft-delete (move to Trash, default) (NEW)
DELETE /v1/tools/email_delete_email?email_service_id=svc_01...&message_id=42&mailbox=INBOX
# → 204 No Content

# Hard-delete (EXPUNGE) (NEW)
DELETE /v1/tools/email_delete_email?email_service_id=svc_01...&message_id=42&mailbox=INBOX&hard=true
# → 204 No Content
```

As MCP tool calls (for MCP clients):

```json
{ "tool": "email_list_mailboxes", "arguments": { "email_service_id": "svc_01..." } }
// → { "mailboxes": [{"name": "INBOX", ...}, {"name": "Sent", ...}] }

{ "tool": "email_list_emails",
  "arguments": { "email_service_id": "svc_01...", "mailbox": "INBOX", "limit": 20, "offset": 0 } }
// → { "messages": [...], "next_cursor": null }

{ "tool": "email_fetch_message",
  "arguments": { "email_service_id": "svc_01...", "message_id": "42", "mailbox": "INBOX" } }
// → { "uid": 42, "subject": "Hello", "from": "alice@…", "body": "…" }

{ "tool": "email_move_email",
  "arguments": { "email_service_id": "svc_01...", "message_id": "42", "from_mailbox": "INBOX", "to_mailbox": "Archive" } }
// → { "message_id": "42", "mailbox": "Archive" }

{ "tool": "email_mark_email",
  "arguments": { "email_service_id": "svc_01...", "message_id": "42", "mailbox": "INBOX", "add": ["\\Seen"], "remove": [] } }
// → { "message_id": "42", "flags_updated": true }

{ "tool": "email_delete_email",
  "arguments": { "email_service_id": "svc_01...", "message_id": "42", "mailbox": "INBOX" } }
// → 204 (soft-delete: moved to Trash)

{ "tool": "email_send",
  "arguments": {
    "email_service_id": "svc_01...",
    "to": ["bob@example.com"],
    "subject": "Report",
    "body": "See attached."
  }
}
// → { "message_id": "<id>", "status": "sent" }
```

**Per-service SMTP routing (PR #156):** There are no global SMTP defaults. The
`smtp_host` and `smtp_port` stored on the registered email service are used directly for
every outbound send. Operators must set both fields correctly when registering a service —
leaving them blank will cause `email_send` to fail. Update them via Admin UI → Email
Services → Edit if you need to change routing.

**Important behavioural notes:**

- **Email body content is never stored by Mintkey.** The MCP server fetches body content
  from email-proxy on each `email_fetch_message` call; no email body persists in Postgres.
- **You NEVER see the upstream password or OAuth2 token.** email-proxy holds the credential
  internally for the duration of the IMAP/SMTP operation, then discards it — same invariant
  as the HTTP proxy.
- **OAuth2 services (Gmail, Outlook) handle token refresh automatically.** If an access token
  is expired, email-proxy refreshes it via the admin-api without any action from you. If the
  refresh token itself is revoked by the provider, the tool call returns
  `503 email_service_auth_expired` — the operator must re-authorize in the Admin UI.
- **Message IDs** are provider UIDs (integers or strings depending on the IMAP server).
  Always use IDs returned by `email_search_messages` or `email_fetch_message`; do not
  construct them yourself.
- **Do NOT route email tool calls through the HTTP proxy (`:8000`).** Email is handled
  exclusively by the email-proxy on `:8088` via these MCP tools.
</email_services>

<errors_and_revocation>
The proxy and MCP tools return errors with a structured `mintkey:code` field in the response body (for HTTP errors) or in the error frame (for streaming MCP). Handle these distinct cases:

| HTTP / Code | `mintkey:code` | Meaning | Action |
|---|---|---|---|
| 401 | `token_expired` | Your brokered JWT TTL elapsed. | Call `request_token` again with your API key. |
| 401 | `token_invalid` | Token signature failed or `kid` unknown. | Refresh; if still failing, your API key may be wrong. |
| 401 | `agent_revoked` | The operator revoked your Agent. | **Stop**. Tell the operator. Do not retry. |
| 401 | `tenant_deleted` | Your tenant was deleted (cascade). | **Stop permanently.** All your access is gone. |
| 403 | `permission_denied` | No active permission grant for this service. | Ask operator to grant access. |
| 403 | `constraint_violated` | Rate limit / time window / path / source-IP violation. Body has `constraint` field with details. | Wait / change request / ask operator to widen the grant. |
| 404 | `unknown_service` | `service_id` doesn't exist or isn't visible to your Agent. | Re-list with `list_services`. |
| 404 | `path_not_allowed` | Path isn't in the service's allowed prefixes (or your grant's). | Check `describe_service` `your_constraints.request_path_prefix`. |
| 400 | `credential_passthrough_forbidden` | You included the upstream's credential header. | Remove the header; Mintkey injects it. |
| 5xx | `upstream_error` | Backend service returned 5xx. Body has the upstream's original response. | Retry with backoff if appropriate. Mintkey does NOT auto-retry. |

**Reading denial responses (post-OPS-LL).** Every 403 from request_token now
carries `agent_id`, `service_id`, `action`, and a `hint` string. Echo the hint
verbatim to whoever is operating you — it contains the exact remediation step
(which agent, which service, which action). Do NOT retry after a 403 unless
the hint says to (rate_limit hints suggest backoff; permission_not_found
means stop and ask the operator).

**Revocation semantics** (ADR-0006 + ADR-0016.7):
- **In-flight read-only tool calls** when your Agent is revoked: complete with current snapshot.
- **In-flight state-changing tool calls** (`request_token`): abort with `503 tenant_deleted` or `401 agent_revoked`.
- **New calls after revocation**: 401 immediately.
- **Streaming MCP connections**: server emits a final error frame, then EOF/connection close.

**Token cache TTL.** If you cache descriptive metadata from `list_services` or `describe_service`, cap it at 5 minutes — Mintkey's change channel can revoke / re-grant within seconds, and your cache will go stale.
</errors_and_revocation>

<conventions>
- **IDs** are prefixed-ULIDs, case-sensitive: `svc_<26-char-Crockford-base32>` for services, `agt_<...>` for agents, `tnt_<...>` for tenants, `pmg_<...>` for permission grants, `svckey_<...>` for classical service API keys (ADR-0018; agent flavor uses the brokered-JWT flow you read above, not service keys).
- **Timestamps**: RFC 3339 UTC always. Do not assume your local timezone.
- **Wire encoding**: JSON for everything. UTF-8.
- **Secrets hygiene**: never log, never echo to conversation context, never persist in long-term memory: your `mk_agentkey_…`, your brokered JWT, or any retrieved upstream credential value (you shouldn't see those anyway — but if you do, treat them as toxic).
- **Tracing**: Mintkey supports OpenTelemetry. If you set `Traceparent` or `X-Trace-Id` headers, the proxy propagates them. Useful for correlating your runtime's traces with Mintkey's.
- **Idempotency**: if you need idempotent upstream calls, send the upstream's idempotency key in the request headers — Mintkey passes them through unchanged.
</conventions>

<security_notes>
- **The brokered JWT is bearer-class.** Anyone with the token can act as you until it expires. Protect it like a session cookie.
- **The Mintkey API key (`mk_agentkey_…`) is much more sensitive** — long-lived, allows minting new JWTs. Treat it like a long-lived password.
- **You will never see the upstream credential** (the real Stripe/Twilio/CRM key). If a tool response contains one, that's a Mintkey bug — report it.
- **Audit**: every proxy call and every state change emits an audit event. The operator can investigate any suspicious activity. Be predictable.
</security_notes>

<references>
- ADR-0006: token format and binding (JWS Ed25519, JWKS, `cnf.jkt`).
- ADR-0007: proxy deployment topology (URL forms, virtual-host alias).
- ADR-0008: multi-tenancy (RLS, tenant context).
- ADR-0009: MCP server stack (Python, `mcp` SDK, HTTP/SSE default).
- ADR-0013: AdminJS UI conventions (operator-facing — not directly relevant to agents).
- ADR-0016: corrections — §16.7 covers revocation semantics, §16.4 covers Constraints schema (rate_limit / time_window / request_path_prefix / source_ip_allowlist).
- ADR-0017: wire-level decisions — error code conventions (`mintkey:code = …`).
- ADR-0018: classical service API keys for non-agent clients.

If anything in this document is stale relative to those ADRs, the ADRs win.
</references>

<minimal_complete_example>
End-to-end (curl, single agent flow):

```bash
# 0. The operator gave you this API key:
export MK_KEY="mk_agentkey_01HKJ7GZ8N0PQR3STUV4WXYZ2A"
export MK_MCP="http://localhost:8082"  # Replace with bootstrap.mcp_url if running on a different host
export MINTKEY_PROXY_URL="http://localhost:8000"  # Replace with bootstrap.proxy_url if running on a different host

# 1. Exchange for a brokered token.
TOKEN=$(curl -s -X POST "$MK_MCP/tools/call" \
  -H "Content-Type: application/json" \
  -d "{\"tool\":\"request_token\",\"arguments\":{\"api_key\":\"$MK_KEY\"}}" \
  | jq -r '.token')

# 2. Find a service.
curl -s -X POST "$MK_MCP/tools/call" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool":"list_services","arguments":{}}'
# → {"services":[{"service_id":"svc_01HKJ7G...","slug":"demo-crm",...}]}

# 3. Call the service through the proxy.
curl -X GET \
  -H "Authorization: Bearer $TOKEN" \
  "$MINTKEY_PROXY_URL/v1/call/svc_01HKJ7G2X3Y4Z5A6B7C8D9E0F1/v1/customers/42"
# → {"customer_id":42,"name":"Acme Corp",...}
```

That's it. You're using Mintkey.
</minimal_complete_example>
