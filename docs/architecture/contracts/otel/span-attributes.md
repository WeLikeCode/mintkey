# Mintkey OTel span-attribute contracts

Stability tier: **experimental**.

This file is the authoritative list of Mintkey-specific span attributes emitted
across all Mintkey services. The SDK-level redaction filter (`otelinit` Go
package / `otel_redaction.py` Python module) enforces that attributes whose name
ends in a forbidden suffix (`_token`, `_secret`, `_password`, etc.) are replaced
with `[REDACTED]` before export.

New attributes **MUST** be added here AND to both OTel allowlists:
- `packages/go/otelinit/allowlist.go`
- `packages/python/mintkey-models/mintkey_models/otel_redaction.py`

---

## Core broker attributes

| Attribute name           | Type   | Description |
| ------------------------ | ------ | ----------- |
| `mintkey.tenant_id`      | string | Prefixed ULID of the tenant (`tenant_…`). |
| `mintkey.agent_id`       | string | Prefixed ULID of the agent (`agent_…`). |
| `mintkey.service_id`     | string | Prefixed ULID of the service (`svc_…`). |
| `mintkey.action`         | string | Permission scope/action string (e.g. `read:contacts`). |
| `mintkey.key_version`    | int    | Credential key version resolved for this request. |
| `mintkey.jti`            | string | ULID-encoded JWT ID. |
| `mintkey.auth_scheme`    | string | Auth scheme name (e.g. `bearer_token`, `ssh_private_key`). |

## SSH proxy attributes (ADR-0022)

| Attribute name             | Type   | Description |
| -------------------------- | ------ | ----------- |
| `ssh.session_id`           | string | Prefixed ULID of the SSH session (`session_…`). |
| `ssh.target_address`       | string | `host:port` of the backend SSH server. |
| `ssh.auth_method`          | string | `jwt` or `api_key`. |

## Email proxy attributes (ADR-0024)

| Attribute name                  | Type   | Description |
| ------------------------------- | ------ | ----------- |
| `email.service_id`              | string | Prefixed ULID of the email service (`svc_…`). |
| `email.message_id`              | string | RFC 5322 Message-ID or IMAP UID of the message. |
| `email.mailbox`                 | string | IMAP mailbox path (e.g. `INBOX`, `Archive`). |
| `email.provider`                | string | OAuth2 provider name: `gmail` or `outlook`. |
| `email.attachment_count`        | int    | Number of attachments on the processed message. |
| `email.body_size_bytes`         | int    | Decoded plain-text body size in bytes. |

> **Redaction note**: `email.message_id` may contain an RFC 5322 angle-bracket
> address-like value. It does NOT contain credential material and is NOT subject
> to value-pattern redaction. Body content, subject, and recipient addresses are
> NEVER recorded as span attributes.

---

## Allowlist maintenance

Every attribute listed in the "Email proxy" section above must also appear in:

1. `packages/go/otelinit/allowlist.go` — `emailAllowedAttrs` map (Go services).
2. `packages/python/mintkey-models/mintkey_models/otel_redaction.py` — `EMAIL_SPAN_ATTRS` frozenset (Python services).

Failure to add an attribute to the allowlist causes it to be redacted by the
SDK-level filter, producing `[REDACTED]` in exported spans.
