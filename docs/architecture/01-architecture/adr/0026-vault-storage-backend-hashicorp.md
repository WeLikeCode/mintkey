# ADR-0026: Vault Adapter storage backend — HashiCorp Vault (KV v2), opt-in

## Status
Proposed — 2026-06-22.

Implements the v2 backend deferred by [ADR-0021](0021-vault-storage-backend-postgres.md) §Alternatives ("HashiCorp Vault (ADR-0003 v2 backend) — Still planned as v2; deferred.") and named as the lead candidate in open-question [OQ-003](../open-questions.md#oq003--vault-adapter-horizontal-scaling-) (Vault Adapter horizontal scaling).

Amends nothing. Adds a third value to the [ADR-0021](0021-vault-storage-backend-postgres.md) backend selector (`MINTKEY_VAULT_BACKEND=hashicorp`). Postgres remains the default; SQLite remains the opt-in offline fallback. The KEK/DEK envelope scheme ([ADR-0003](0003-credential-storage-strategy.md) §Decision 2) is unchanged.

> **Closes [OQ-003](../open-questions.md#oq003--vault-adapter-horizontal-scaling-).** OQ-003 listed three candidates for the Vault Adapter horizontal-scaling story; candidate (a) — "bring HashiCorp Vault forward as v2" — is selected and realised by this ADR. The HashiCorp backend is a network-addressable, replicated store, removing the single-writer constraint of the v1 SQLite file backend that motivated the question. See [§ OQ-003 resolution](#oq-003-resolution).

---

## Context

The Vault Adapter (container C6) stores envelope-encrypted credentials in a pluggable backend selected by `MINTKEY_VAULT_BACKEND`. Two concrete backends ship today, per [ADR-0021](0021-vault-storage-backend-postgres.md):

- **`postgres`** (default post-2026-05-31) — `vault.credentials` table, `vault` schema, in the existing `mintkey` DB. Captured by a single `pg_dump`; RLS-isolated; concurrent `Put` serialised by `pg_advisory_xact_lock`.
- **`sqlite`** (opt-in fallback) — single encrypted file on a mounted volume, for offline/embedded deploys with no Postgres.

Three forces motivate a third backend:

1. **HashiCorp Vault was always the planned v2 store.** [ADR-0003](0003-credential-storage-strategy.md) §Decision 3 names "v2 backend: HashiCorp Vault" explicitly. [ADR-0021](0021-vault-storage-backend-postgres.md) advanced the *v1* file backend to Postgres "without requiring a new container" and recorded HashiCorp Vault as "still planned as v2; deferred." This ADR pays down that deferral.

2. **OQ-003 names it as the lead candidate.** [OQ-003](../open-questions.md#oq003--vault-adapter-horizontal-scaling-) (Vault Adapter horizontal scaling, 🟢 Medium, Phase 2) records that once the proxy-plugin plaintext cache was dropped ([ADR-0014.4](0014-iter-1-2-corrections.md)), every proxy request hits the Vault Adapter, and the single-writer file backend has no horizontal-scaling story. Candidate (a) — bring HashiCorp Vault forward — is listed first.

3. **Operators already run HashiCorp Vault.** Operators whose environment standardises on HashiCorp Vault want the most sensitive Mintkey data — encrypted credentials — to live in their existing, audited, access-controlled secrets platform rather than in a Mintkey-managed Postgres schema. A native store removes a parallel system of record.

**Storage model (does not deviate from [ADR-0003](0003-credential-storage-strategy.md)).** Mintkey's KEK/DEK envelope (AES-256-GCM, per-credential DEK wrapped by a single KEK — [ADR-0003](0003-credential-storage-strategy.md) §Decision 2) is **unchanged**. HashiCorp Vault is used as an opaque key/value substrate for the already-encrypted `wrapped_dek` and `enc_payload` blobs plus their metadata — exactly the role Postgres and SQLite play today. We do **not** push plaintext into HashiCorp's Transit engine, and we do **not** store plaintext in KV. The new backend is a `store.Backend` implementation, nothing more.

The Kiro spec for this feature lives at [`.kiro/specs/vault-backend-hashicorp/`](../../../../.kiro/specs/vault-backend-hashicorp/) (`requirements.md`, `design.md`, `tasks.md`).

---

## Decision

Add a `*HashiCorpStore` implementing the existing `store.Backend` interface (`Put`, `Get`, `Revoke`, `ListVersions`, `Close`). Select it with `MINTKEY_VAULT_BACKEND=hashicorp`. The new value is **additive**: `postgres` (default when unset), `sqlite`, and the existing unknown-backend error path behave exactly as today.

### Storage substrate — KV v2 as opaque envelope storage

HashiCorp Vault **KV v2** is used as **opaque storage** for the already-encrypted envelope blobs (`wrapped_dek`, `enc_payload`) plus metadata. The Mintkey **KEK never leaves the adapter** — it is loaded locally from `MINTKEY_VAULT_KEK_FILE` ([ADR-0003](0003-credential-storage-strategy.md)) and is never transmitted to HashiCorp Vault. Only ciphertext is written:

- `wrapped_dek` — the per-credential DEK, already wrapped by the local KEK.
- `enc_payload` — the credential, already encrypted under the DEK.

Both are AEAD ciphertext from the adapter's perspective; HashiCorp Vault never sees plaintext and is not trusted for confidentiality of the credential. A credential blob is **byte-identical** across the Postgres, SQLite, and HashiCorp backends.

### Transit engine NOT used

HashiCorp Vault's **Transit** (server-side encryption) engine is deliberately **not** used. Mintkey owns its KEK/DEK envelope ([ADR-0003](0003-credential-storage-strategy.md) §Decision 2); routing encryption through Transit would duplicate or displace that scheme and shift confidentiality trust to HashiCorp for a property Mintkey already owns. KV v2 is an opaque blob store and nothing more.

### Authentication — AppRole with background token renewal

The backend authenticates to HashiCorp Vault using **AppRole** (`role_id` + `secret_id` → client token). A background goroutine renews the token before its TTL expires (via the `vaultapi` `LifetimeWatcher`); on renewal failure it re-logs in with capped backoff and logs a fixed message **without** the token. The renewal goroutine is started only from the store constructor (no `init()` side effects) and is cancelled by `Close()`. The `secret_id` and the issued client token **never** appear in any log line, error message, or OTel span attribute — consistent with the [ADR-0017.6](0017-round-3-corrections.md) span-attribute denylist (`*_token`, `*_secret`).

### KV path layout

KV v2 stores secret data under `<mount>/data/<path>` and metadata under `<mount>/metadata/<path>`. Mintkey's layout, with the configurable prefix:

```
<mount>/data/<prefix>/<tenant_id>/<service_id>/v<N>      # one credential version (N = key_version)
<mount>/data/<prefix>/<tenant_id>/<service_id>/_index    # per-(tenant,service) version index doc
```

- **Version doc** (`.../v<N>`) — a JSON value map carrying every `CredentialRecord` field the SQLite backend persists (`credential_id`, `key_version`, `auth_scheme`, `wrapped_dek`, `enc_payload`, `is_current`, `is_revoked`, `created_at`, `target_url`, `header_name`, `query_param`, `target_address`, `ssh_user`). The `[]byte` fields (`wrapped_dek`, `enc_payload`) are base64-std-encoded. `tenant_id`/`service_id` are implied by the path and also stored in the doc for self-description. The Postgres-JOIN-only fields (`ServiceBaseUrl`, `TlsInsecureSkipVerify`, SMTP/IMAP) are left empty/zero, exactly as SQLite leaves them.
- **Index doc** (`.../_index`) — `{"current": <N>, "max": <N>, "versions": [...]}`. `Put` reads `_index`, computes `next = max+1`, writes `v<next>` as `is_current=true`, flips the prior current version's `is_current=false`, then writes `_index` back with a KV v2 **CAS** check (against the index's metadata version) to detect concurrent writers. An in-process **per-(tenant,service) mutex** is the primary serialiser; CAS is the second-line defence — the same two-layer pattern as the Postgres advisory-lock + UNIQUE-constraint approach.

### Read / revoke / list semantics (parity with both existing backends)

- `Get(0)` → read `_index.current`, then read `v<current>`; `Get(N>0)` → read `v<N>` directly.
- A missing KV path (nil `*Secret` / nil `.Data`) maps to a wrapped `sql.ErrNoRows` so `errors.Is(err, sql.ErrNoRows)` holds — parity with `postgres.go` and `sqlite.go`.
- `Revoke(N)` → `ErrRevokeCurrent` if the target is current; otherwise set `is_revoked=true`. Missing version → wrapped `sql.ErrNoRows`.
- `ListVersions` returns metadata-only records ordered by ascending `key_version`, filtered `> afterKeyVersion`, with `limit` clamped to 50 when 0 or > 200.

### Tenant isolation — application-side, by path prefix

Tenant isolation is enforced **application-side** by the KV path prefix (`<prefix>/<tenant_id>/...`). There is no Postgres-RLS equivalent in HashiCorp Vault, which is acceptable because the adapter is the **sole writer** and always scopes reads by `(tenant_id, service_id)`. RLS is a Postgres concept and does not transfer; one mount with app-layer scoping is the v1 model (see [§ Alternatives](#alternatives-considered)).

### What does NOT change

- **No Liquibase change.** No new table, no migration changeset. The schema source of truth ([ADR-0015](0015-liquibase-schema-source-of-truth.md)) is untouched.
- **No SQLAlchemy / `vault.proto` change.** No change to the `CredentialRecord` struct, the gRPC contract, or the admin-api mirror.
- **No `main.go` change to SSH wiring.** The vault-adapter `cmd/` SSH-RPC wiring uses a `st.(*store.PostgresStore)` type assertion; with the HashiCorp backend selected that assertion fails and `SSHVaultAdapter` is disabled — exactly as it already does for SQLite. SSH RPCs remain Postgres-only.

---

## Consequences

### Positive

- **Native store for HashiCorp operators.** Operators who already run HashiCorp Vault get a first-class Mintkey backend; the most sensitive data lives in their existing secrets platform.
- **Envelope reused verbatim.** The KEK/DEK scheme ([ADR-0003](0003-credential-storage-strategy.md) §Decision 2) is unchanged. A credential blob is byte-identical across Postgres, SQLite, and HashiCorp — the migration tool verifies this with a 5-sample `bytes.Equal` round-trip.
- **No Liquibase change.** Because HashiCorp Vault is an opaque blob store, no schema migration, no SQLAlchemy mirror diff, and no `vault.proto` change are required ([ADR-0015](0015-liquibase-schema-source-of-truth.md) is untouched).
- **Closes [OQ-003](../open-questions.md#oq003--vault-adapter-horizontal-scaling-).** A network-addressable, replicated credential store replaces the single-writer file backend on the proxy hot path.
- **Non-destructive cut-over.** Like [ADR-0021](0021-vault-storage-backend-postgres.md), the migration leaves the source store in place; rollback is flipping `MINTKEY_VAULT_BACKEND` back and restarting the adapter.

### Costs

- **New compose service.** Dev/CI gains a `hashicorp-vault` container (community edition, profile-gated to `hashicorp`). When the backend is selected at runtime, HashiCorp Vault becomes a runtime dependency.
- **AppRole must be provisioned.** Operators must enable AppRole, write a Mintkey policy scoped to `<mount>/data/<prefix>/*` and `<mount>/metadata/<prefix>/*`, and supply `role_id` + `secret_id`. This is more setup than the zero-dependency Postgres/SQLite paths.
- **SSH RPCs remain Postgres-only.** `SSHVaultAdapter` is gated on the Postgres backend; selecting HashiCorp disables SSH credential serving, identical to the SQLite limitation. Operators needing SSH stay on Postgres.
- **No per-tenant AppRoles in v1.** One AppRole and one mount serve all tenants; isolation is application-side via the path prefix. Per-tenant AppRoles/mounts are deferred (see [§ Alternatives](#alternatives-considered)).

### Risks

- **KV v2 list semantics differ from SQL.** KV v2 has no `ORDER BY` / `MAX()`; a small per-(tenant,service) `_index` doc maintains the version list and current pointer to avoid mount scans on the hot path. The in-process per-key mutex plus KV v2 CAS guards against concurrent-`Put` version collisions.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| **HashiCorp Transit engine** (server-side encryption — encrypt/wrap inside Vault rather than storing opaque ciphertext) | Rejected. Would duplicate or displace Mintkey's own KEK/DEK envelope ([ADR-0003](0003-credential-storage-strategy.md) §Decision 2) and shift confidentiality trust to HashiCorp for a property Mintkey already owns. Mintkey keeps its local KEK and writes opaque ciphertext; KV v2 is a blob store, nothing more. |
| **Per-tenant AppRole + per-tenant mount** | Rejected for v1. One mount with an application-side path prefix (`<prefix>/<tenant_id>/...`) is simpler, and the adapter is the only writer and always scopes reads by `(tenant_id, service_id)`. Per-tenant AppRoles/mounts add provisioning and lifecycle complexity without a v1 isolation requirement that the path prefix does not already meet. Revisit if a high-isolation tier ([ADR-0008](0008-multi-tenancy-row-level-with-db-tier.md) DB-per-tenant analogue) demands cryptographic tenant separation in HashiCorp. |
| **Make HashiCorp the default backend** | Rejected. Postgres remains the default ([ADR-0021](0021-vault-storage-backend-postgres.md)); HashiCorp is opt-in. Defaulting to it would impose a HashiCorp Vault dependency on every deployment, contrary to the zero-external-dependency posture ([ADR-0003](0003-credential-storage-strategy.md) §Consequences). |
| **Remove the Postgres or SQLite backends** | Rejected. Both remain: Postgres is the default and the only SSH-capable store; SQLite is the offline/embedded escape hatch ([ADR-0021](0021-vault-storage-backend-postgres.md)). HashiCorp is a third option behind the same interface. |

---

## Environment variables

All seven new variables MUST appear in `.env.example` with an explanatory comment (project guardrail). `MINTKEY_VAULT_BACKEND` is the existing selector gaining a new value.

| Env var | Default | Validation | Purpose |
|---|---|---|---|
| `MINTKEY_VAULT_BACKEND` | `postgres` | one of `postgres` \| `sqlite` \| `hashicorp` | Backend selector (existing; new `hashicorp` value). |
| `MINTKEY_VAULT_HASHICORP_ADDR` | _(none)_ | required when backend=hashicorp; must be a URL (`http(s)://host:port`) | HashiCorp Vault API address (dev: `http://hashicorp-vault:8201`). |
| `MINTKEY_VAULT_HASHICORP_MOUNT` | `secret` | non-empty | KV v2 mount path. |
| `MINTKEY_VAULT_HASHICORP_PREFIX` | `mintkey` | non-empty; no leading/trailing `/` | Path prefix under the mount. |
| `MINTKEY_VAULT_HASHICORP_ROLE_ID` | _(none)_ | required when backend=hashicorp | AppRole `role_id`. |
| `MINTKEY_VAULT_HASHICORP_SECRET_ID` | _(none)_ | required when backend=hashicorp; **SENSITIVE — never logged** | AppRole `secret_id`. |
| `MINTKEY_VAULT_HASHICORP_NAMESPACE` | `` (empty) | optional | Vault Enterprise namespace (ignored by community edition). |
| `MINTKEY_VAULT_HASHICORP_CACERT` | `` (empty) | optional path | CA certificate for TLS to Vault (production). |

When `MINTKEY_VAULT_BACKEND=hashicorp`, `store.NewFromEnv` builds the config from these vars; missing-config errors MUST name the specific missing variable (e.g. `MINTKEY_VAULT_BACKEND=hashicorp requires MINTKEY_VAULT_HASHICORP_ROLE_ID`), matching the style of the existing `postgres`/`sqlite` branches.

---

## OQ-003 resolution

[OQ-003](../open-questions.md#oq003--vault-adapter-horizontal-scaling-) (Vault Adapter horizontal scaling, 🟢 Medium, Phase 2) asked for a horizontal-scaling story for the Vault Adapter once the proxy-plugin plaintext cache was dropped ([ADR-0014.4](0014-iter-1-2-corrections.md)) and every proxy request began hitting the adapter. It listed three candidates:

- **(a)** bring HashiCorp Vault forward as v2 — *selected and realised by this ADR;*
- (b) read-mostly Vault Adapter replicas with file replication;
- (c) gRPC load balancer in front of stateless Vault Adapter instances sharing storage.

This ADR selects **(a)**. With `MINTKEY_VAULT_BACKEND=hashicorp`, credential storage moves to a network-addressable, independently replicable HashiCorp Vault cluster — removing the single-writer constraint of the v1 SQLite file backend that motivated the question. Candidates (b) and (c) remain available for the Postgres/SQLite backends but are not required once HashiCorp Vault is an option. **OQ-003 is marked `Closed by ADR-0026` in [`open-questions.md`](../open-questions.md).**

---

## Related

- [ADR-0003](0003-credential-storage-strategy.md) — pluggable Vault Adapter; KEK/DEK envelope; names HashiCorp Vault as the v2 backend (this ADR realises it). The envelope scheme is reused verbatim.
- [ADR-0011](0011-shared-go-stack.md) — shared Go stack (`pgx/v5`, `slog`, `testcontainers-go`, distroless); the `hashicorp` backend uses `github.com/hashicorp/vault/api` (+ `/api/auth/approle`) within that stack and is tested with `testcontainers-go`.
- [ADR-0021](0021-vault-storage-backend-postgres.md) — backend selector and Postgres default; this ADR adds the third `hashicorp` value additively, leaving Postgres the default and SQLite the opt-in fallback.
- [OQ-003](../open-questions.md#oq003--vault-adapter-horizontal-scaling-) — Vault Adapter horizontal scaling; **closed by this ADR** (candidate (a) selected).
- [ADR-0017.6](0017-round-3-corrections.md) — span-attribute denylist (`*_token`, `*_secret`); the AppRole `secret_id` and client token fall under it and are never logged or spanned.
- [`.kiro/specs/vault-backend-hashicorp/`](../../../../.kiro/specs/vault-backend-hashicorp/) — requirements, design, and tasks for the implementation.
