# Contracts

Status: **iteration 4 contracts (draft)**.

This is where the *wire-level* contracts live. Iteration 1 stood up a
skeleton; iteration 4 (this round) lands the typed schemas.

Stability tier: **experimental** for v1. All artifacts use
`version: "0.1.0-preview.1"`.

## Surfaces and files

| Surface                       | File                                                | Format                       |
| ----------------------------- | --------------------------------------------------- | ---------------------------- |
| Admin REST API (operators)    | [`rest/openapi.yaml`](rest/openapi.yaml)            | OpenAPI 3.1                  |
| MCP tools (agents)            | [`mcp/tools.yaml`](mcp/tools.yaml)                  | MCP `2024-11-05` + JSON Schema 2020-12 |
| Audit events                  | [`events/audit-event.schema.json`](events/audit-event.schema.json) | JSON Schema 2020-12          |
| Change-channel events         | [`events/change-event.schema.json`](events/change-event.schema.json) | JSON Schema 2020-12          |
| OTel span attributes          | [`events/span-attributes.md`](events/span-attributes.md) | Prose + closed allowlist     |
| Vault Adapter gRPC IDL        | [`vault-adapter/vault.proto`](vault-adapter/vault.proto) | proto3                       |

### [`rest/`](rest/) — Admin REST API

Operator-facing, machine-friendly. Specified as **OpenAPI 3.1**. Both URL
forms are documented (per ADR-0008): explicit
`/v1/tenants/{tenant_id}/...` (canonical) and implicit `/v1/...`
(session-derived). Errors are RFC 7807 `application/problem+json` with
`mintkey:code` and `mintkey:trace_id` extensions. Sensitive fields
(plaintext credentials, plaintext Agent API Keys) are marked
`x-mintkey-sensitive: true` and returned only on the immediate creation
response.

### [`mcp/`](mcp/) — MCP tool definitions

Agent-facing. Each tool is a typed MCP definition (`name`,
`description`, `input_schema`, `output_schema`, `errors`, `examples`).
Tenant comes from the agent's authentication context (Agent API Key) and
is NEVER a tool parameter (per ADR-0009).

### [`events/`](events/) — internal event schemas and OTel conventions

Append-only audit events, change-channel reference events, and the OTel
span allowlist + redaction policy. Audit and change events are
discriminated by `event_type` and share the field naming with the REST
schemas (e.g. `service.registered` audit payload mirrors the REST
`Service` create response).

### [`vault-adapter/`](vault-adapter/) — gRPC IDL

The internal contract between the Egress Proxy plugin / Admin REST API
and the Vault Adapter. proto3, package `mintkey.vault.v1`. Per ADR-0008
every RPC is tenant-scoped.

## Conventions

- **Schema-first**: contracts are written before code; clients and
  server stubs are generated from them.
- **Versioning**: every contract carries an explicit `version`;
  breaking changes require a new path/tool name and a deprecation
  window.
- **Stability tiers**: `experimental` -> `stable` -> `deprecated`.
  Stability is per surface, not per project. v1 is `experimental`
  end-to-end.
- **Time**: RFC 3339 UTC.
- **IDs**: ULIDs (Crockford base32, 26 chars), prefixed by resource
  type (`tenant_…`, `operator_…`, `agent_…`, `svc_…`, `cred_…`,
  `perm_…`, `audit_…`, `change_…`, `session_…`).
- **Multi-tenancy**: every endpoint, tool, and event is tenant-scoped
  (ADR-0008). The explicit URL form is canonical for REST; MCP tools
  resolve tenant from auth context.
- **Sensitive fields**: marked `x-mintkey-sensitive: true` (OpenAPI),
  `x-mintkey-sensitive: true` in tool output schemas (MCP), and
  explicitly commented `SENSITIVE` in the `.proto`.

## Cross-file consistency

Several invariants are pinned across files; changing one requires
changing all of them:

- The `auth_scheme` enum appears in OpenAPI (`AuthScheme`),
  audit-event payload schemas, and the Vault Adapter proto
  (`AuthScheme`). Same seven values; same names. (mtls added per ADR-0016.5/ADR-0017.)
- The `event_type` enums for audit and change events use the same
  dotted strings (`service.registered`, `credential.rotated`, …);
  audit has more event types than the change channel.
- The OpenAPI `Service` schema and the `service.registered` audit
  payload share field names (`service_id`, `name`, `base_url`,
  `auth_scheme`, `actions`).
- The REST `mintkey:code` values, the audit `reason_code` enums, the
  MCP error codes, and the OTel `mintkey.error.code` attribute share
  vocabulary; the OpenAPI document's `x-mintkey-error-codes` is the
  authoritative list.


## REST `mintkey:code` ↔ MCP `error_code` mapping

Both vocabularies are closed enums. The full table lives in [ADR‑0017.10](../01-architecture/adr/0017-round-3-corrections.md). REST and MCP share most codes; new additions to either require an ADR.
