# Agent service credential

## Purpose

A publisher agent writes the credential of a service it owns and never reads it back. The credential is bound to the
service's target and stored so that the proxy connects only to public addresses. The audit contract lists the events these
routes write.

## ADDED Requirements

### Requirement: A credential is written, never read, and bound to its target
`PUT /v1/agent/services/{service_ref}/credential` SHALL read its JSON body itself, not through request-model validation, so
that no refusal echoes the input: it SHALL answer 422 `{"code": "mintkey:validation_failed", "field": <name>, "title": <fixed
text>}` for a body that is not a JSON object, has a key other than `value`, `header_name` and `query_param`, or has a bad
field. It accepts `{value, header_name?, query_param?}`, `value` 1 to 8192 characters without CR, LF or NUL, for an owned
service only, resolved through `require_owned_service(..., for_update=True)`. A service whose `auth_scheme` is not one of
`bearer_token`, `api_key_header`, `api_key_query`, `basic_auth` SHALL answer 422 `mintkey:validation_failed` with `field`
`auth_scheme`. `api_key_header` needs `header_name` (`^[A-Za-z0-9-]{1,64}$`, not `host`, `content-length`,
`transfer-encoding`, `connection` or `x-mintkey-*`, any case), `api_key_query` needs `query_param`
(`^[A-Za-z0-9_.-]{1,64}$`), the other schemes take neither. The route SHALL call `VaultAdapterClient.put_credential` once
with the service's `auth_scheme`, `base_url` as `target_url` and `egress_scope="public"` (the parameter of
`proxy-public-egress`); in the request's transaction supersede the active `credentials` rows of the service, insert the new
metadata row and set `services.current_key_version`; write `service.credential.set`; and answer 200 with exactly
`{service_id, credential_set: true, updated_at}`. Neither the response, an audit payload, nor any statement parameter SHALL
contain the value, a hash, a prefix, a length or a fingerprint of it. A vault failure SHALL answer 502
`mintkey:vault_unavailable` before any metadata statement or event.

#### Scenario: a bearer credential
- **WHEN** a publisher puts the value `s3cret-value-123` on an owned `bearer_token` service
- **THEN** `put_credential` was called once with that value as `plaintext`, the base URL as `target_url` and `egress_scope`
  `public`, and no statement names `egress_scope`; the answer has exactly the three keys; and the text of the
  response, of every `audit_emit` call and of every statement and its parameters does not contain `s3cret-value-123`

#### Scenario: header and query names
- **WHEN** an `api_key_header` service gets no `header_name`, `Host`, `X-Mintkey-Test`, then `X-Api-Key`; a `bearer_token`
  service gets a `header_name`; an `api_key_query` service gets no `query_param`
- **THEN** all but the fourth answer 422 `mintkey:validation_failed`; the fourth answers 200 with `X-Api-Key` passed to
  `put_credential`

#### Scenario: bad values, other owners, a failing vault, an unsupported scheme
- **WHEN** the value is empty, 8193 characters long or `s3cret-value-123` plus a line feed; the service belongs to another
  agent; `put_credential` raises; or the service's scheme is `ssh_private_key`
- **THEN** the answers are 422 `mintkey:validation_failed` three times (no body contains `s3cret-value-123`), 403
  `mintkey:not_owner`, 502 `mintkey:vault_unavailable` and 422 `mintkey:validation_failed` with `field` `auth_scheme`; no
  metadata statement and no event ran, and `put_credential` was not called for the last

#### Scenario: the row is locked before the vault write
- **WHEN** a publisher writes a credential on an owned service
- **THEN** the first statement that names `services` after the tenant context contains `FOR UPDATE`, `put_credential` was
  called after it, and every metadata statement and `audit_emit` call came after `put_credential`

### Requirement: The new events are in the audit contract
`audit-event.schema.json` SHALL define `ev_service_credential_set` (payload `{service_id, key_version, auth_scheme}`) and
`ev_service_credential_cleared` (`{service_id, reason, fields_changed}`), all keys required, `additionalProperties` false,
none holding a credential, each in `oneOf` and `discriminator.mapping`. It SHALL add `owner_agent_id` to the payload
properties of `ev_service_registered` without adding it to `required`, and add `auth_scheme` to the `fields_changed` enum of
`ev_service_updated`, which keeps its six values.

#### Scenario: the contract lists them
- **WHEN** the schema is loaded as JSON
- **THEN** the two definitions, their mapping and `oneOf` entries exist with those keys; `owner_agent_id` is a property of
  `ev_service_registered` and is not in its `required` list; the `fields_changed` enum is `display_name`, `description`,
  `base_url`, `actions`, `openapi_url`, `status`, `auth_scheme`
