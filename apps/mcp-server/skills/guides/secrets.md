# Guide: Agent-stored secrets

URI: `mintkey://guides/secrets` · also `mintkey_bootstrap(section="secrets-guide")`

Agent secrets are a **HashiCorp-Vault-KV-style** store for secrets that the
AGENT itself owns and must read back — a DB password, a service-account JSON, an
SSH private key. They are encrypted at rest and identified by a `sec_` wire ID
plus a human-readable `name` (ADR-0025).

## Agent-stored secrets vs. operator-managed service credentials — DON'T confuse them
| | Agent-stored secret (this guide) | Operator-managed service credential |
|---|---|---|
| Who supplied the plaintext | YOU (the agent) | the operator, at service registration |
| Can the agent read it back | YES — that's the whole point | NO — never visible to the agent |
| How accessed | `secret_get` returns the plaintext | injected by the proxy in-flight; you never see it |
| Tools | `secret_put/get/list/delete` | `mintkey_request_token` + proxy call |
| Needs `request_token`? | NO | YES |

Use `secret_put` ONLY for values your agent owns and needs to retrieve. Do NOT
put an upstream service's URL or credential in `secret_put` to "call it later" —
that is the proxy's job (`mintkey://guides/rest-api`). `secret_put` is config
the agent holds, not a way to reach operator-registered services.

## Authentication: your `mk_agent_` key directly — nothing else
Secret tools do NOT use brokered JWTs. Do NOT call `mintkey_request_token` for
them — there is no `read:secrets` action to request, and secrets are not in
`permission_grants`. Authorization is by ownership: you can always operate on
your OWN secrets, and READ secrets an operator shared with you. Send your
`Authorization: Bearer mk_agent_<key>` header; that's it.

## The 4 tools
| Tool | Who may call | REST endpoint | Notes |
|---|---|---|---|
| `secret_put` | owner | `POST /v1/tools/secret_put` | create (version=1) or overwrite (version++) |
| `secret_get` | owner or shared-with | `GET /v1/tools/secret_get?secret_id=sec_…` | returns plaintext (query param, not path) |
| `secret_list` | owner or shared-with | `GET /v1/tools/secret_list` | metadata only, NO values; cursor paging |
| `secret_delete` | owner only | `DELETE /v1/tools/secret_delete?secret_id=sec_…` | permanent; cascades share grants; idempotent |

### Store (2-step total: just put — no token needed)
```json
{ "tool": "secret_put",
  "arguments": { "name": "db-password", "value": "s3cr3t",
                 "content_type": "text/plain" } }
// → { "secret_id": "sec_01HX...", "name": "db-password", "version": 1 }
```
### Read it back
```json
{ "tool": "secret_get", "arguments": { "secret_id": "sec_01HX..." } }
// → { "secret_id":"sec_01HX...", "name":"db-password", "version":1,
//      "value":"s3cr3t", "access":"owner" }
```
### List (owned + shared, never values)
```json
{ "tool": "secret_list", "arguments": {} }
// → { "secrets":[{ "secret_id":"sec_01HX...", "name":"db-password",
//        "version":1, "size_bytes":6, "access":"owner",
//        "created_at":"...", "updated_at":"..." }], "next_cursor": null }
```
### Delete (owner only, permanent)
```json
{ "tool": "secret_delete", "arguments": { "secret_id": "sec_01HX..." } }
// → {}  (200)
```

## Validation & limits
- `name` must match `^[a-zA-Z0-9._-]{1,128}$`; else `422 invalid_argument`.
- `value` ≤ 65,536 bytes UTF-8; base64-encode binary yourself; else `422`.
- `content_type` is an optional free-text hint (e.g. `application/json`).

## Scope rules
- Secrets are **per-(tenant, agent, name)** — your tenant comes from your API key,
  never from a tool argument; cross-tenant access is impossible by construction.
- Names are **unique per owning agent** — `secret_put` with an existing name
  overwrites and increments `version`.
- An owning agent always sees its own secrets; a recipient agent sees a shared
  secret with `access: "shared"`.

## Operator-provisioned & shared secrets (ADR-0025 D7)
Agents CANNOT grant each other access. **Sharing is operator-managed**: a tenant
operator creates an `agent_secret_grant` (admin-api) from an owner's secret to a
recipient agent. After that, the recipient can `secret_get`/`secret_list` it and
sees `access: "shared"`; only the OWNER can `secret_put` (overwrite) or
`secret_delete`. Operators can also pre-seed secrets that an agent reads at
startup — your code should `secret_list` on boot to discover what it has rather
than assume. To request a new shared secret or a pre-seeded value, ask the
operator; there is no agent-side share API.

## Safety invariants
- **Plaintext is NEVER in logs, audit payloads, OTel span attributes, or
  change-events.** The value appears ONLY in the `secret_get` response body
  (marked `x-mintkey-sensitive`). Values are envelope-encrypted (AES-256-GCM,
  fresh DEK per write, wrapped under the vault KEK) before storage.
- **Every read is audited** (`agent_secret.read` with secret_id/version/
  reader_agent_id/access — never the value). Creates/updates/deletes audit too.
- **Anti-enumeration**: `secret_get` and `secret_delete` return the SAME
  `404 secret_not_found` whether the secret doesn't exist OR exists but isn't
  visible to you — you cannot probe for others' secrets.
- **Deletion is permanent** — metadata row + vault blob + share grants (CASCADE)
  all gone. No soft-delete, no recovery.

## Anti-patterns
- Putting an upstream service credential/URL in `secret_put` to call it yourself → use the proxy; that credential is operator-managed.
- Calling `mintkey_request_token` before a secret tool → secrets use your API key directly; no JWT.
- Trying to share a secret agent-to-agent → ask the operator; sharing is operator-managed.
- Logging the `secret_get` value → it is sensitive; keep it in memory only.
