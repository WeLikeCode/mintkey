---
inclusion: fileMatch
fileMatchPattern: "apps/admin-api/**,apps/mcp-server/**,apps/broker/**,apps/proxy-plugin/**,apps/kong-syncer/**,apps/vault-adapter/**,apps/admin-ui/**,docs/architecture/**"
---

# Security and Tenancy

Conventions for every component that touches auth, credentials, or tenant context.

## Tenancy model (ADR-0008)

- Multi-tenant by architecture, single-tenant by default UX.
- Default isolation: row-level (`tenant_id UUID NOT NULL` on every domain table + Postgres RLS).
- Opt-in: DB-per-tenant for high-isolation deployments (`MINTKEY_TENANT_ISOLATION=database`).
- Every DB transaction sets `SET LOCAL app.current_tenant = '<uuid>'` before any query.
- Application uses the `mintkey_app` Postgres role. Superuser is reserved for migrations only.

## JWT claims (ADR-0006, ADR-0008)

Every brokered token carries:

```json
{
  "iss": "mintkey/broker",
  "sub": "agent_<ulid>",
  "aud": "svc_<ulid>",
  "tnt": "<tenant_id>",
  "scope": "<action>",
  "jti": "<ulid>",
  "iat": 1715000000,
  "exp": 1715000600
}
```

- `tnt` is mandatory. The Egress Proxy validates `tnt` matches the registered service's tenant on every request.
- A token issued in tenant A cannot validate against a service in tenant B.
- Default TTL: 10 minutes. Configurable per service.
- Revocation: `jti` denylist in Postgres + change-channel propagation ≤ 5 s (ADR-0016).

## Credential handling rules (P-1)

- Credentials are decrypted only inside the Vault Adapter.
- Plaintext is consumed only inside the Egress Proxy's request mutation step.
- Plaintext is zeroed after each request scope.
- No plaintext credential cache in the proxy plugin (ADR-0014).
- No credential value in any log, trace span, or response body visible to the agent.

## Operator authentication (ADR-0005)

- Default IdP: Keycloak (OIDC). Swappable via env vars.
- Internal fallback: username + Argon2id password (bootstrap admin + break-glass).
- Sessions: HttpOnly Secure SameSite=Strict cookie; server-side session store in Postgres.
- CSRF tokens on all state-changing endpoints.
- Roles (`Admin`, `Auditor`, `AgentOwner`) live in our Identity service, not in the IdP.
- `PlatformAdmin` is a boolean on `Operator`; every cross-tenant action it performs emits an audit event.

## Agent authentication

- Agent API Key: 32-byte random, format-prefixed, hashed at rest (Argon2id), constant-time compare.
- Agent API Key is shown once on creation; never retrievable again.
- Revocation propagates via change channel within ≤ 5 s.

## Encryption at rest (ADR-0003)

- v1 (default): per-credential DEK (AES-256-GCM); KEK from keyfile or env var on mounted volume.
- v2 (Phase 2): HashiCorp Vault Transit as KEK source.
- v3 (Phase 2): SQL + external KMS (cloud KMS or HSM).
- AEAD on all ciphertext — tamper detected on decrypt.
- KEK rotation re-wraps DEKs in place; no full re-encryption of credential table.

## Audit requirements (P-2, ADR-0014)

- Every state-change emits via `audit.emit(event_type, actor, target, before, after)`.
- Audit table is append-only with mandatory per-tenant hash chain.
- Every audit event carries `tenant_id`.
- Audit query is tenant-scoped; `PlatformAdmin` cross-tenant queries themselves emit audit events.
- Retention: retain chain as compliance record; GDPR erasure case is an open question (OQ-001).

## SSRF and egress controls

- Proxy egress allowlist: registered base URL of the bound service only.
- No redirect following to other origins.
- RFC1918 / link-local destinations refused by default; opt-in for explicit dev mode.
- Per-service registered hostname + TLS verification on registration.
