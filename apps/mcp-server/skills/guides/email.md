# Guide: Using an email service through Mintkey

URI: `mintkey://guides/email` · also `mintkey_bootstrap(section="email-guide")`

Email services are handled by the **email-proxy** (a separate Go binary, REST
API on port `:8088`), NOT the Kong HTTP proxy and NOT the SSH bastion. You use
the 9 `email_*` MCP tools; the email-proxy holds the IMAP/SMTP credential and
performs the protocol operation — you never see the password or OAuth2 token.

## IMPORTANT — how to invoke email tools today
The `email_*` tools are exposed as **REST endpoints under `/v1/tools/email_*`**,
NOT through the MCP JSON-RPC `tools/list`/`tools/call` surface. A pure
MCP-over-JSON-RPC client will NOT find them via `tools/list` and cannot run them
via `tools/call` (the dispatcher has no `email_*` branch). Call them as HTTP
requests to the MCP server with your agent key:
```
Authorization: Bearer mk_agent_<your-key>
```
Each tool internally exchanges a brokered email JWT and calls the email-proxy —
you do NOT call `mintkey_request_token` yourself for the normal MCP-tool path.
(Direct path, if you want it: call `mintkey_request_token(service_id, action)`,
which for an email service returns `{token, service_kind:"email",
email_proxy_url}`, then call `{email_proxy_url}/v1/email-proxy/*?service_id=<id>`
with `Authorization: Bearer <token>`.)

## Detecting an email service
In discovery, an email service has `kind: "email_service"`,
`connect_type: "email"`, `auth_scheme` in `{email_password, email_oauth2,
email_app_password}`, and fields `imap_host` / `smtp_host` /
`allowed_recipient_domains`. (`services.base_url` is NULL for email services —
addressing lives in the `email_services` row, ADR-0024 corrigendum.)

## Grant requirements (per-action scopes, ADR-0024 D3)
The operator must grant the agent an `email_permission_grant` on the service.
The 4 scopes and the tools they unlock:
| Scope | Tools |
|---|---|
| `read:email` | `email_list_mailboxes`, `email_search_messages`, `email_fetch_message`, `email_list_emails`, `email_download_attachment` |
| `send:email` | `email_send` |
| `write:email` | `email_move_email`, `email_mark_email` |
| `delete:email` | `email_delete_email` |
Scope model (Option A): the broker currently emits ALL 4 scopes on every email
JWT; the email-proxy enforces per-endpoint scope checks. If no grant exists you
get `403 permission_not_found` — ask the operator to add one in the Admin UI.

OAuth2 (Gmail/Outlook, `email_oauth2`) additionally requires the operator to
configure per-tenant OAuth2 client credentials (Admin UI → Email → OAuth2
Providers) and authorize once; otherwise `503 oauth2_not_configured`. Token
refresh is automatic; if the refresh token is revoked you get
`503 email_service_auth_expired` and the operator must re-authorize.

## Credential injection
You never hold the mailbox password / OAuth2 token. The MCP tool gets a brokered
email JWT; the email-proxy validates it against the broker JWKS, sets tenant
context from the JWT `tnt` claim, fetches the credential from the vault, runs the
IMAP/SMTP operation, then discards the credential — same S-SEC-1 invariant as the
HTTP proxy. Email body content is fetched per call and never persisted in Postgres.

## The 9 tools → IMAP/SMTP operations
All accept `email_service_id` (canonical) OR `service_id` (alias). The exact
parameter names below match the implementation (`apps/mcp-server/.../email_*.py`),
which is authoritative over tools.yaml where they differ.

| Tool | Scope | Method + REST path | IMAP/SMTP op |
|---|---|---|---|
| `email_list_mailboxes` | read | `GET /v1/tools/email_list_mailboxes?email_service_id=` | IMAP LIST |
| `email_list_emails` | read | `GET /v1/tools/email_list_emails?email_service_id=&mailbox=INBOX&limit=50&offset=0` | UID listing (paged) |
| `email_search_messages` | read | `GET /v1/tools/email_search_messages?email_service_id=&query=<RFC3501>&mailbox=INBOX` | IMAP SEARCH |
| `email_fetch_message` | read | `GET /v1/tools/email_fetch_message?email_service_id=&message_id=<UID>&mailbox=INBOX` | IMAP FETCH (envelope+body) |
| `email_download_attachment` | read | `GET /v1/tools/email_download_attachment?email_service_id=&message_id=<UID>&part_id=<pid>&mailbox=INBOX` | FETCH BODY[part] |
| `email_send` | send | `POST /v1/tools/email_send` (JSON body) | SMTP send |
| `email_move_email` | write | `POST /v1/tools/email_move_email` (JSON body) | IMAP MOVE (COPY+STORE+EXPUNGE fallback) |
| `email_mark_email` | write | `POST /v1/tools/email_mark_email` (JSON body) | IMAP STORE ±FLAGS |
| `email_delete_email` | delete | `DELETE /v1/tools/email_delete_email?email_service_id=&message_id=<UID>&mailbox=INBOX[&hard=true]` | soft (→Trash) or hard (EXPUNGE) |

### Read flow (list mailboxes → list/search → fetch)
```bash
GET /v1/tools/email_list_mailboxes?email_service_id=svc_01...
# → { "mailboxes": ["INBOX","Sent","Drafts","[Gmail]/Spam"] }

GET /v1/tools/email_search_messages?email_service_id=svc_01...&query=FROM "alice@example.com" UNSEEN&mailbox=INBOX
# → { "messages": [ { "uid": 42, "subject": "...", "from": "alice@example.com" }, ... ] }

GET /v1/tools/email_fetch_message?email_service_id=svc_01...&message_id=42&mailbox=INBOX
# → { "uid": 42, "subject": "...", "from": "...", "body": "...", "parts": [...] }
```
Always use UIDs returned by search/fetch; never construct message IDs yourself.

### Send (POST JSON; field is `body`; HTML is `html_body`)
```bash
POST /v1/tools/email_send
Content-Type: application/json
{ "email_service_id": "svc_01...", "to": ["bob@example.com"],
  "subject": "Report", "body": "See attached.",
  "cc": ["carol@example.com"], "html_body": "<p>See attached.</p>" }
# → { "message_id": "<id>", "status": "sent" }
```
Recipients are RFC 5322 validated and checked against `allowed_recipient_domains`;
`\r\n` in headers is rejected. SMTP host/port come from the service row — no
global SMTP default; if unset, `email_send` fails.

### Manage (move / mark / delete) — parameter names follow the IMPL
```bash
# Move — body uses from_mailbox / to_mailbox
POST /v1/tools/email_move_email
{ "email_service_id":"svc_01...", "message_id":"42",
  "from_mailbox":"INBOX", "to_mailbox":"Archive" }
# → { "message_id":"42", "mailbox":"Archive" }

# Mark — body uses add / remove flag lists (\\Seen, \\Flagged, \\Answered)
POST /v1/tools/email_mark_email
{ "email_service_id":"svc_01...", "message_id":"42", "mailbox":"INBOX",
  "add":["\\Seen"], "remove":["\\Flagged"] }
# → { "message_id":"42", "flags_updated": true }

# Delete — soft by default (move to Trash); hard=true → EXPUNGE
DELETE /v1/tools/email_delete_email?email_service_id=svc_01...&message_id=42&mailbox=INBOX
# → 204 (soft, moved to Trash)
DELETE /v1/tools/email_delete_email?email_service_id=svc_01...&message_id=42&mailbox=INBOX&hard=true
# → 204 (EXPUNGE)
```

### Attachments
```bash
GET /v1/tools/email_download_attachment?email_service_id=svc_01...&message_id=42&part_id=2&mailbox=INBOX
# → { "filename":"report.pdf", "content_type":"application/pdf",
#      "size":12345, "content_base64":"..." }
```
`part_id` is the IMAP BODYSTRUCTURE part number (e.g. "2", "2.1"), discovered
from `email_fetch_message`'s `parts[]`.

## Common patterns
- Process unread: `email_search_messages?query=UNSEEN` → `email_fetch_message` per UID → act → `email_mark_email add:["\\Seen"]`.
- Reply: `email_fetch_message` the original (for `from`/`subject`) → `email_send` with `to:[original.from]`, `subject:"Re: …"`.
- Archive: `email_move_email from_mailbox:"INBOX" to_mailbox:"Archive"`.

## Anti-patterns
- Calling `email_*` via MCP `tools/call` → not registered there; call the `/v1/tools/email_*` REST endpoints with your agent key.
- Routing email through the HTTP proxy (`:8000`) or SSH bastion (`:2222`) → email is the email-proxy (`:8088`) via these tools only.
- Constructing message UIDs yourself → only use IDs from search/fetch (UIDs are provider-specific).
- Sending `body_html` → the field is `html_body`; `body` is the plain-text part.
- Expecting `email_send` to work with blank SMTP config → operator must set smtp_host/smtp_port on the service.
