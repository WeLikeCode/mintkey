# OpenTelemetry span attribute conventions

**Stability tier**: experimental. **Version**: `0.1.0-preview.1`.

This document is the *closed* allowlist of OTel attributes Mintkey emits.
Every container's OTel SDK is configured with a span processor that drops
any attribute not on this list. The redaction policy below is enforced by
a CI test (`tests/observability/test_span_attributes.py`).

Cross-references:
- Container view: `docs/01-architecture/02-container-view.md`.
- Audit events (separate stream): `docs/contracts/events/audit-event.schema.json`.
- Multi-tenancy: ADR-0008. Tenant id is on every span.

## Naming convention

Mintkey-emitted spans MUST be named `mintkey.<container>.<operation>`:

| Span name                              | Container         | Operation                                                    |
| -------------------------------------- | ----------------- | ------------------------------------------------------------ |
| `mintkey.broker.issue_token`           | Credential Broker | Mint a brokered JWT (one span per `request_token` call).     |
| `mintkey.broker.jwks_serve`            | Credential Broker | Serve `/.well-known/jwks.json`.                              |
| `mintkey.proxy.handle_request`         | Egress Proxy      | One span per inbound proxied request.                        |
| `mintkey.proxy.verify_token`           | Egress Proxy      | JWT verification (signature, claims, revocation).            |
| `mintkey.proxy.fetch_credential`       | Egress Proxy      | Vault Adapter call from the plugin.                          |
| `mintkey.proxy.forward_backend`        | Egress Proxy      | Outbound HTTP to the registered backend.                     |
| `mintkey.vault.encrypt`                | Vault Adapter     | One span per `PutCredential` envelope-encrypt.               |
| `mintkey.vault.decrypt`                | Vault Adapter     | One span per `GetCredential` envelope-decrypt.               |
| `mintkey.vault.kek_load`               | Vault Adapter     | KEK source read at startup or on rotation.                   |
| `mintkey.mcp.tool_call`                | MCP Server        | One span per tool invocation; `mintkey.mcp.tool_name` set.   |
| `mintkey.adminapi.endpoint`            | Admin REST API    | One span per inbound REST call; `http.route` set.            |
| `mintkey.kongsyncer.push_config`       | Kong-syncer       | One span per declarative-YAML push to Kong's `/config`.      |
| `mintkey.changes.publish`              | Admin REST API    | One span per `NOTIFY` published.                             |
| `mintkey.changes.consume`              | Subscribers       | One span per change-channel event consumed (incl. heartbeat).|

Spans from upstream libraries (FastAPI, asyncpg, gRPC, etc.) keep their
canonical OTel-semconv names; the same redaction rules apply.

## Required attributes per span

These attributes MUST be set on every Mintkey span, on top of OTel
semantic-convention attributes already provided by the SDK:

| Attribute                     | Type   | Notes                                                                  |
| ----------------------------- | ------ | ---------------------------------------------------------------------- |
| `mintkey.tenant_id`           | string | UUID of the active tenant. Empty only on `mintkey.adminapi.endpoint` for unauthenticated routes (`/v1/auth/login`, `/v1/health`, `/v1/ready`, `/.well-known/jwks.json`). |
| `mintkey.actor_id`            | string | Prefixed-ULID of the actor (`operator_…` / `agent_…` / `system_…`).    |
| `mintkey.actor_type`          | string | Enum: `operator`, `agent`, `system`, `platform_admin`.                 |
| `mintkey.request_id`          | string | ULID assigned by the inbound middleware; propagated as `X-Request-Id`. |

For `mintkey.proxy.handle_request` additionally:

| Attribute                     | Type   | Notes                                                                  |
| ----------------------------- | ------ | ---------------------------------------------------------------------- |
| `mintkey.service_id`          | string | ULID-prefixed (`svc_…`).                                               |
| `mintkey.action`              | string | The scope/action (e.g. `read:contacts`).                               |
| `mintkey.jti`                 | string | ULID — the JWT's `jti` claim.                                          |
| `mintkey.key_version`         | int    | Credential `key_version` injected on this request.                     |
| `mintkey.outcome`             | string | Enum: `success`, `client_error`, `server_error`, `denied`, `error`.    |
| `mintkey.auth_method`         | string | Enum: `brokered_jwt`, `api_key`. ADR-0018 §2.6; Req 11.4.             |

Note: `key_fingerprint` is NOT a span attribute — it is audit-only.

## Allowed attributes (closed allowlist)

Any attribute not listed below is dropped at the SDK layer. The list is
deliberately small.

### Mintkey-specific (`mintkey.*`)

| Attribute                              | Type   | Where used                                                         |
| -------------------------------------- | ------ | ------------------------------------------------------------------ |
| `mintkey.tenant_id`                    | string | Every span.                                                        |
| `mintkey.tenant_slug`                  | string | Optional convenience for log-correlation; never PII.               |
| `mintkey.actor_id`                     | string | Every span.                                                        |
| `mintkey.actor_type`                   | string | Every span.                                                        |
| `mintkey.request_id`                   | string | Every span.                                                        |
| `mintkey.session_id`                   | string | Admin REST API authenticated routes only.                          |
| `mintkey.service_id`                   | string | Broker, proxy, MCP `describe_service`, Kong-syncer.                |
| `mintkey.action`                       | string | Broker, proxy.                                                     |
| `mintkey.jti`                          | string | Broker (set), proxy (read).                                        |
| `mintkey.key_version`                  | int    | Broker, proxy, vault, change-events.                               |
| `mintkey.outcome`                      | string | Broker, proxy.                                                     |
| `mintkey.tool_name`                    | string | MCP `tool_call`.                                                   |
| `mintkey.cache_status`                 | string | `hit` / `miss` / `bypass` (proxy, MCP).                            |
| `mintkey.change_event_type`            | string | `mintkey.changes.publish`, `mintkey.changes.consume`.              |
| `mintkey.change_event_id`              | string | `mintkey.changes.publish`, `mintkey.changes.consume`.              |
| `mintkey.kong.config_version`          | string | `mintkey.kongsyncer.push_config`.                                  |
| `mintkey.vault.backend`                | string | `file` / `vault` / `sql_kms`.                                      |
| `mintkey.vault.kek_version`            | int    | Vault Adapter spans.                                               |
| `mintkey.error.code`                   | string | `mintkey:code` value when the request failed (matches REST codes). |
| `mintkey.deny.reason_code`             | string | Set on `mintkey.proxy.handle_request` when `outcome=denied`.       |
| `mintkey.auth_method`                  | string | Enum: `brokered_jwt`, `api_key`. Proxy only. ADR-0018 §2.6.        |
| `mintkey.stability_tier`               | string | Constant `experimental` for v1.                                    |

### OTel semantic-convention (`http.*`, `rpc.*`, `db.*`, `messaging.*`, `error.*`)

The following standard attributes are allowed verbatim. Any other
semantic-convention attribute is dropped.

- `http.request.method`
- `http.response.status_code`
- `http.route`            (templated path; never the raw path with PII)
- `url.scheme`
- `server.address`
- `server.port`
- `network.peer.address`
- `network.peer.port`
- `rpc.service`
- `rpc.method`
- `rpc.system`            (e.g. `grpc`)
- `rpc.grpc.status_code`
- `db.system`             (e.g. `postgresql`)
- `db.operation`
- `messaging.system`      (e.g. `postgres_listen_notify`)
- `messaging.destination.name`
- `messaging.operation`
- `error.type`
- `exception.type`
- `exception.message`     (after redaction; see policy below)

### Resource attributes (set once per process)

- `service.name`          (e.g. `mintkey.broker`, `mintkey.proxy`)
- `service.version`       (e.g. `0.1.0-preview.1`)
- `service.instance.id`
- `deployment.environment` (`dev` / `staging` / `prod` / `compose`)

## Redaction policy

The following attributes and span fields are FORBIDDEN. The CI test
asserts none of them appear in any sample trace.

1. **HTTP authentication / authorization headers**: never recorded. The SDK
   strips:
   - `http.request.header.authorization`
   - `http.request.header.cookie`
   - `http.request.header.proxy-authorization`
   - `http.response.header.set-cookie`
   - `http.response.header.www-authenticate`
2. **Plaintext credentials in any form**:
   - `mintkey.credential.value`           (forbidden)
   - `mintkey.credential.plaintext`       (forbidden)
   - `mintkey.credential.client_secret`   (forbidden)
   - `mintkey.token`                      (forbidden) — the JWT itself.
   - `mintkey.api_key`                    (forbidden) — the Agent API Key.
   - `mintkey.password`                   (forbidden)
3. **Body fields with credential signatures**:
   - Any attribute whose name ends in `.password`, `.secret`, `.token`,
     `.api_key`, `.client_secret`, `.session` is dropped.
   - Any attribute whose value matches the per-service credential
     signature regexes (configured per service `auth_scheme`) is replaced
     with `«redacted»` and a `mintkey.error.code = credential_echo_detected`
     attribute is added.
4. **Raw URL paths and query strings** are NEVER set as span attributes.
   Only templated routes (`http.route`) and a fixed allowlist of safe
   query parameters (`limit`, `after`, `event_type`, `name_contains`) are
   recorded.
5. **Exception messages** are recorded only after passing through the
   same redaction filters; stack traces are recorded but the SDK truncates
   each frame's locals.
6. **Personally identifiable info** (email addresses, IPs, user-agents)
   is recorded only on `mintkey.adminapi.endpoint` spans for auth-related
   routes, and only as a salted hash for IPs in `prod`.

The SDK's redaction filter runs on every `OnEnd` callback before the
span is exported.

## Trace context propagation

- **Standard**: W3C Trace Context (`traceparent`, `tracestate`).
- **Inbound**: every Mintkey container parses `traceparent` from inbound
  HTTP and gRPC and continues the trace; missing `traceparent` starts a
  new trace.
- **Outbound**: every Mintkey container injects `traceparent` on outbound
  HTTP and gRPC. The Egress Proxy injects `traceparent` on the request to
  the backend.
- **Baggage**: only ONE `baggage` key is allowed: `mintkey.tenant_id`.
  Any other baggage key is stripped at ingress and not propagated. No PII
  in baggage — ever. The CI test enforces this.

## Sampling strategy

| Environment | Head-based sampler                                     | Tail-based override                                                                |
| ----------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `dev`       | `AlwaysOn` (100%)                                      | None.                                                                              |
| `staging`   | `TraceIdRatioBased(0.10)` (10%)                        | Force-keep on errors and on `latency > 1 s`.                                       |
| `prod`      | `TraceIdRatioBased(0.01)` (1%)                         | Force-keep on errors, on `latency > p99-of-rolling-30-min`, on `outcome=denied`.   |

Sampling uses parent-based decisions: child spans honor the parent's
decision. Tail sampling is implemented in the OTel Collector
(`tailsamplingprocessor`); the SDKs export at the head-based rate plus
all explicitly force-keep flagged spans.

## Default OTel SDK config

- Language SDKs: Python (`opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`,
  `opentelemetry-instrumentation-asyncpg`, `opentelemetry-instrumentation-grpc`),
  Go (`go.opentelemetry.io/otel`, `otelgrpc`, `otelhttp`, `otelsql`).
- Exporter: OTLP/gRPC to the local OTel Collector at
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`.
- Resource attributes injected from `OTEL_RESOURCE_ATTRIBUTES`:
  `service.name`, `service.version`, `deployment.environment`.
- Batch span processor with default tuning; deviations specified in
  iteration-2 closeout.
- Custom span filter: `MintkeyAttributeAllowlistProcessor` runs before the
  exporter and drops disallowed attributes.

## CI enforcement

The redaction allowlist is a hard test, not a lint:
- `tests/observability/test_span_attributes_allowlist.py` instantiates
  every container's tracer, executes a representative request, captures
  the exported spans, and asserts that the *attribute keys* are a subset
  of the allowlist.
- `tests/observability/test_span_attributes_redaction.py` injects known
  credential strings and asserts none appear in any span attribute or
  exception field.
- A failing CI run blocks the merge.

Adding a new attribute requires editing this file *and* updating the
allowlist constant in `mintkey/internal/otel/allowlist.go` and
`mintkey_otel/allowlist.py`.


### Redaction policy — extended (per ADR-0017.6)

Forbidden span attribute name patterns (case-insensitive). Any attribute matching these patterns MUST be dropped at the SDK layer; CI redaction tests assert no surviving attribute matches:

- `mintkey.token` (exact)
- `mintkey.api_key` (exact)
- `mintkey.password` (exact)
- `*_token` (suffix; covers `mintkey.access_token`, `mintkey.refresh_token`, `mintkey.id_token`, `mintkey.session_token`, `mintkey.csrf_token`, `mintkey.bootstrap_token`)
- `*_secret` (suffix; covers `mintkey.client_secret`, `mintkey.signing_secret`, `mintkey.shared_secret`)
- `*_password` (suffix)
- `*_passphrase` (suffix)
- `mintkey.authorization_header` (exact)
- `mintkey.cookie_value` (exact)
- `mintkey.set_cookie_value` (exact)
- Any attribute whose value matches the credential signature regex `^(sk|pk)_[a-zA-Z0-9_-]{20,}$` or `eyJ[A-Za-z0-9+/=._-]{20,}` (JWT shape) — flagged at runtime + emit `proxy.credential_echo_detected` audit if it appears in a proxy span.

`mintkey.tenant_id` is the only PII-adjacent attribute permitted in baggage; anything else is dropped from baggage at the SDK layer.
