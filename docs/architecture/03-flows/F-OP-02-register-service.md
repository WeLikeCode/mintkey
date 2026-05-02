# F‑OP‑02 — Register a service (with optional OpenAPI link)

## Goal
A logged‑in operator registers a new backend service in the active tenant; an optional OpenAPI URL is attached for downstream agent discovery.

## Actors
- **Operator** (browser, AdminJS).
- **Admin API**, **Postgres**, **change channel** (Postgres LISTEN/NOTIFY).
- Subscribers consuming the resulting `service.registered` event: **Kong‑syncer**, **MCP Server**.

## Pre‑conditions
- [F‑OP‑01](F-OP-01-bootstrap-and-login.md) complete; operator logged in with `role >= AgentOwner`.
- The operator has an active tenant (or `is_platform_admin` and a chosen tenant).

## Post‑conditions
- New row in `services` with `tenant_id`, `name`, `base_url`, `auth_scheme`, optional `openapi_url`, optional `openapi_etag`, `created_by = operator_id`.
- `service.registered` audit event with payload referencing the new service.
- `service.registered` change event published on `mintkey:service` channel.
- Kong‑syncer pushes updated declarative YAML to Kong.
- MCP Server invalidates its discovery cache for the tenant.

## Sequence diagram

```mermaid
sequenceDiagram
    actor Op as Operator
    participant UI as AdminJS
    participant API as Admin API
    participant DB as Postgres
    participant Bus as PG LISTEN/NOTIFY
    participant Kos as Kong-syncer
    participant Kong
    participant MCP as MCP Server

    Op->>UI: Services → New
    Op->>UI: name, base_url, auth_scheme, openapi_url (optional)
    Op->>UI: Save
    UI->>API: POST /v1/tenants/t_default/services<br/>Authorization Bearer signed-jwt
    API->>API: validate signed JWT (per ADR-0014.6), RBAC, tenant scope
    API->>API: validate input (Pydantic): URL form, no RFC1918 unless allowlisted
    API->>DB: BEGIN
    API->>DB: SET LOCAL app.current_tenant = $tid
    API->>DB: INSERT services
    API->>DB: INSERT audit service.registered
    API->>Bus: NOTIFY mintkey:service { event_type: service.registered, tenant_id, service_id }
    API->>DB: COMMIT
    API-->>UI: 201 Created (Service)
    UI-->>Op: detail page with the service
    Bus-->>Kos: service.registered for tenant_id
    Kos->>API: GET /v1/tenants/$tid/services
    Kos->>Kong: POST /config — declarative YAML with new route for the service
    Kong-->>Kos: 200
    Bus-->>MCP: service.registered
    MCP->>MCP: invalidate discovery cache for tenant
```

## Quality attribute scenarios touched
- [S‑AUD‑1](../01-architecture/03-quality-attributes.md) — service registration audited.
- [S‑MT‑1](../01-architecture/03-quality-attributes.md) — tenant scoping enforced via RLS + middleware.
- [S‑OPS‑2](../01-architecture/03-quality-attributes.md) — change propagation to Kong via the syncer.

## Failure modes
| Failure | Detection | Behavior |
|---------|-----------|----------|
| Invalid `base_url` (non‑https in non‑dev mode) | Pydantic validator | 422 with field error |
| Internal IP without explicit allowlist | server‑side check (per [ADR‑0007](../01-architecture/adr/0007-proxy-deployment-topology.md)) | 422 |
| Duplicate service name within tenant | Postgres unique constraint | 409 with `mintkey:code = service_name_taken` |
| Operator lacks `AgentOwner+` role | RBAC check | 403 |
| `openapi_url` unreachable (validation only — best‑effort) | optional probe times out | warning; service still saved |
| Change channel publish fails | inside the same transaction → rollback | DB has no row, no audit, no notification — caller gets 500 |
| Kong‑syncer push fails | retry with backoff; alarm after N failures | service is in DB but Kong has stale config — reconciliation job catches it on next pull |

## Test plan

### Unit tests
- `service.input_validator` — base_url URL form, scheme (`http` rejected outside dev), private IP rejection, name uniqueness pre‑check.
- `service.create_handler` — call sequence: validate → INSERT → INSERT audit → NOTIFY → COMMIT.
- Pydantic model coverage: every field, every constraint.

### Integration tests (testcontainers — Postgres + Kong + admin‑api + kong‑syncer)
- Happy path: POST → assert row + audit + NOTIFY received by a subscriber stub.
- Concurrent: two operators register two services with the same name → one succeeds, one fails with 409.
- Cross‑tenant: an `AgentOwner` in tenant A cannot create a service in tenant B (URL form: 403; implicit form: targets A).
- Kong‑syncer integration: register service → assert Kong's declarative config has the new route within 2 s.

### Live smoke
- Part of E2E‑01 Phase 3.

## Kiro spec inputs
- **Components**: `admin-api/services/services_handlers.py`, `kong-syncer/internal/syncer.go`, `mintkey-models/Service` schemas.
- **Contract**: `POST /v1/tenants/{tid}/services` in `docs/contracts/rest/openapi.yaml`; `service.registered` in `docs/contracts/events/audit-event.schema.json` and `change-event.schema.json`.
- **Tasks**:
  1. Write integration test asserting the row + audit + NOTIFY pipeline.
  2. Implement Pydantic model + validator.
  3. Implement handler.
  4. Implement Kong‑syncer change‑channel listener and push.
  5. Add concurrent‑duplicate test; fix race if any.
  6. Add cross‑tenant test.
