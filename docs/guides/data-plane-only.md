# Data-plane-only profile

Mintkey's data plane can run on its own: the **broker** issues tokens, the **proxy-plugin**
injects credentials, and a SQLite-backed **vault-adapter** stores them. The control plane is
not required. This guide lists what runs, the settings each process needs, how a request
travels, and what still requires Postgres.

The profile is assembled from the published container images and environment variables; it
is not a separate distribution.

## 1. What runs

Run these three processes:

- `broker` — issues short-lived JWTs and publishes its JWKS.
- `proxy-plugin` — the egress proxy; validates the JWT, fetches and injects the credential,
  and forwards the request to the upstream.
- `vault-adapter` — the credential store, configured with `MINTKEY_VAULT_BACKEND=sqlite` and
  `MINTKEY_VAULT_FILE_PATH` pointing at the SQLite file on a mounted volume.

Do **not** run the control plane:

- `admin-api` — the Admin REST API.
- `Kong` — the egress gateway; the proxy-plugin is called directly in this profile.
- `kong-syncer` — pushes routes to Kong; not needed without Kong.
- `mcp-server` — agent discovery; the embedding application issues tokens itself (section 3).
- `Keycloak` — operator SSO for the admin surfaces.
- the admin UI (AdminJS).

The proxy finds the broker through `BROKER_ADDR` (for JWKS) and the vault through
`VAULT_GRPC_ADDR`; it listens on `PLUGIN_PORT`.

## 2. Keys and identities

Keys live on files, not in the environment:

- `MINTKEY_VAULT_KEK_FILE` — the 32-byte key-encryption key used by `vault-adapter`.
- `MINTKEY_BROKER_SIGNING_KEY_FILE` — the Ed25519 signing key used by `broker`.

The proxy authenticates to the vault with its own service identity:

- `MINTKEY_VAULT_PROXY_IDENTITY_ID`
- `MINTKEY_VAULT_PROXY_TOKEN`

Credentials are written with the vault's `PutCredential` RPC under the admin identity:

- `MINTKEY_VAULT_ADMIN_IDENTITY_ID`
- `MINTKEY_VAULT_ADMIN_TOKEN`

Every `*_TOKEN` is a long random value provisioned as a secret, with the same value on both
sides of the pair. This page shows no values. `MINTKEY_VAULT_PROXY_TOKEN` must match the
value the vault-adapter registered for `MINTKEY_VAULT_PROXY_IDENTITY_ID`; likewise for the
admin pair.

## 3. Issuing tokens

The embedding application calls `POST /v1/issue` on the broker with the header
`X-Mintkey-Service-Token` set to the broker's `MINTKEY_MCP_SERVICE_TOKEN`.

The request body carries:

- `agent_id` — the agent the token is issued to.
- `service_id` — the service the token is scoped to; this becomes the token's audience.
- `tenant_id` — the tenant.
- `scope` — the granted actions.
- `ttl_seconds` — the token lifetime.
- `methods` — optional, restricts the HTTP methods the token may use.
- `path_prefix` — optional, restricts the request paths the token may use.

The broker answers with the signed JWT, which the application hands to the agent.

## 4. Calling a service

The agent (or the application on its behalf) calls the proxy at:

```
/v1/call/<service id>/<path>
```

`<service id>` is the token's `service_id` or its `svc_` wire form. The proxy removes the
`/v1/call/<service id>` prefix, joins the service's base path, and forwards the bare path to
the upstream.

With `MINTKEY_ENV=production` the audience check is strict (`MINTKEY_AUD_ENFORCEMENT`
overrides the default): a request must address the token's service, either in the path or
through the `X-Mintkey-Service-ID` header. A request that addresses no service is answered
`403` with `service not addressed`; a request that addresses another service is answered
`403` with `scope mismatch`.

## 5. Audit events

Both the broker and the proxy emit audit events to `MINTKEY_ADMIN_API_URL`, which points at
the embedding application. The application must answer `POST /v1/internal/audit/emit` with a
2xx response.

The application authenticates the caller by checking `X-Mintkey-Service-Token` against
`MINTKEY_BROKER_SERVICE_TOKEN` for the broker and `MINTKEY_PROXY_SERVICE_TOKEN` for the proxy.
The body is one JSON event with these fields:

- `event_type`
- `tenant_id`
- `actor_id`
- `actor_type`
- `target_id`
- `target_type`
- `payload`

## 6. What needs Postgres

Revocation and budgets need the proxy's `DATABASE_URL`.

Without it, an issued token stays valid until its `exp` plus a 30-second clock skew, and no
budget applies.

With it, the application revokes a token or an agent by sending a `NOTIFY` on the
`mintkey:agent` channel:

- `{"event_type":"token.revoked","jti":...}` for a single token.
- `{"event_type":"agent.revoked","agent_id":...}` for every token of an agent.

Classical service API keys (the non-brokered path) also need the broker's `DATABASE_URL` to
resolve and revoke keys; this profile does not require them for brokered calls.

## 7. Not provided

This profile is documented but not shipped as a runnable bundle:

- There is no compose file for the data-plane-only profile in this repository.
- There is no end-to-end test of the profile; an end-to-end test needs Docker.

Operators assemble the three services themselves. A compose file may be added under
`infra/compose/` separately.

## Related

- The proxy's path handling and audience check: `openspec/changes/proxy-data-plane-paths/`
  (spec `proxy-data-plane-routing`).
- Deployment defaults for the full stack: `infra/compose/docker-compose.yml`.
