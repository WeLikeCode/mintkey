# ADR‑0003: Credential storage — pluggable adapter; v1 backend is an encrypted file on an externally mounted volume

## Status
Accepted — 2026-05-10. Promoted from [`proposal/P-002-credential-storage-strategy.md`](../../proposal/P-002-credential-storage-strategy.md), Option C, with a revised v1 backend choice.

> **AMENDED by ADR-0021 (2026-05-31):** The SQLite v1 backend is demoted to an opt-in fallback. Postgres (`vault.credentials` table, `vault` schema in the `mintkey` DB) is the default backend as of 2026-05-31. The KEK/DEK scheme and the pluggable-adapter architecture are unchanged. See [ADR-0021](0021-vault-storage-backend-postgres.md).

## Context
[P‑002](../../proposal/P-002-credential-storage-strategy.md) considered three options for credential storage:
- (A) HashiCorp Vault as the only backend.
- (B) SQL + envelope encryption against an external KMS.
- (C) Pluggable Vault Adapter that can host multiple backends.

The original recommendation in P‑002 was **(C) with (B) as the v1 implementation**.

On review, the v1 backend is being changed. The first user of Mintkey will be a self‑hoster running `docker compose up` on a laptop or single VM. Requiring them to provision a cloud KMS or stand up a HashiCorp Vault on day zero is a friction we can avoid for the MVP. We can ship a simpler backend now, keep the abstraction clean, and add the production‑grade backends as second and third implementations behind the same interface.

This ADR finalizes both the abstraction (Option C from P‑002) **and** the order in which concrete backends ship.

## Decision

1. **Vault Adapter is a pluggable component (P‑002 Option C).** Every code path that touches a credential goes through the Vault Adapter interface; backends are swappable at deploy time by configuration.

2. **v1 ships exactly one backend: encrypted file on an externally mounted volume.**
   - The file lives on an externally mounted volume so it survives container removal and rebuilds. Docker named volume by default (`mintkey_credentials`); host bind mount supported.
   - **Per‑credential envelope encryption**: each credential has a unique DEK (AES‑256‑GCM, fresh nonce per write). DEKs are wrapped by a single KEK. The KEK is loaded once at startup from one of (in priority order):
     1. A keyfile path (`MINTKEY_VAULT_KEK_FILE`) — recommended.
     2. An env var (`MINTKEY_VAULT_KEK`, base64‑encoded 32 bytes) — fallback for dev only.
     3. Otherwise the process fails closed.
   - File format: a single AEAD‑sealed structured file (JSON‑lines or SQLite — finalized in an iteration‑2 ADR).
   - Writes are atomic: write‑temp + fsync + rename.
   - Permissions: 0600, owned by the service user.

3. **v2 backend: HashiCorp Vault.** Mintkey ships a Vault Adapter implementation that delegates storage to HashiCorp Vault. Two integration depths: (a) Vault as the credential store directly; (b) Vault Transit engine to wrap our DEKs while ciphertext stays in our DB. The choice between (a) and (b) is deferred to the v2 ADR.

4. **v3 backend: SQL + envelope encryption against an external KMS** (cloud KMS or HSM). Same envelope model as v1; the only change is the source of the KEK and the storage of the ciphertext (Postgres rather than file).

This sequencing reverses the P‑002 follow‑up note (which had SQL+KMS first, Vault second). HashiCorp Vault is the more common self‑hosted secrets stack among the audience we expect to graduate from the file backend; SQL+KMS specifically serves cloud‑native deployments and arrives third.

## Configuration shape (preview — finalized in iteration 2)

```
MINTKEY_VAULT_BACKEND=file              # file | vault | sql_kms
MINTKEY_VAULT_FILE_PATH=/var/lib/mintkey/credentials.enc
MINTKEY_VAULT_KEK_FILE=/run/secrets/mintkey_kek
# fallback (dev only):
# MINTKEY_VAULT_KEK=base64:<32 bytes>
```

## Consequences

### Positive
- Mintkey is runnable end‑to‑end with `docker compose up` and zero external dependencies. No KMS to provision, no Vault to install.
- The Vault Adapter abstraction is exercised from day one, so adding Vault and SQL+KMS later is purely an interface‑conforming addition.
- The envelope model (DEK per credential, KEK wraps DEKs) is identical across all three backends; only the source of the KEK and the storage of the ciphertext change.

### Costs and risks
- **Weaker root of trust than KMS‑rooted backends.** An attacker who reads the host's filesystem *and* the KEK source (keyfile or env var) can decrypt all credentials. This is acceptable for the self‑host MVP and dev environments; it is **not** acceptable for compliance‑regulated production.
- **Quality attribute [S‑SEC‑2](../03-quality-attributes.md#ssec2--credentials-at-rest-are-encrypted-with-a-kmsrooted-key) is now backend‑conditional.** The file backend satisfies *confidentiality at rest* but not the *KMS‑rooted* property. S‑SEC‑2 is updated to reflect this and to call out which backends satisfy which response measures.
- **Operator risk: shipping the file backend into production.** Mitigation: the admin console and `/v1/health`/`/v1/ready` responses must surface a prominent warning when a non‑KMS‑rooted backend is in use, and the deployment docs must label the file backend "MVP / development" front‑and‑center.

## Implications elsewhere
- [`02-container-view.md`](../02-container-view.md) — Vault Adapter backend options updated.
- [`03-quality-attributes.md`](../03-quality-attributes.md) — S‑SEC‑2 amended (backend‑conditional response measure).
- [`05-threat-model.md`](../05-threat-model.md) — file backend variant added under information disclosure.
- [`../../00-vision/04-glossary.md`](../../00-vision/04-glossary.md) — Vault entry updated with the new backend list.
- [`../../05-deployment/README.md`](../../05-deployment/README.md) — compose sketch swaps the KMS emulator for an externally mounted credential volume.

## Open follow‑ups (iteration 2)
- File format: JSON‑lines vs. SQLite. Tradeoff is corruption recovery vs. atomic writes.
- KEK rotation procedure for the file backend (re‑wrap all DEKs in place).
- Key derivation: do we KDF the KEK from a passphrase, or require a 32‑byte random key directly? *Leaning: require random; provide a `mintkey vault genkey` CLI helper.*
- DEK cache lifetime (the encrypted DEK can be cached; the plaintext DEK is per‑request).

## Related
- [P‑002 credential‑storage‑strategy](../../proposal/P-002-credential-storage-strategy.md) — Accepted (this ADR).
- [ADR‑0001 record‑architecture‑decisions](0001-record-architecture-decisions.md).
- [ADR‑0002 product‑name‑mintkey](0002-product-name-mintkey.md).
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — credentials carry `tenant_id`; Vault Adapter contract becomes `get_credential(tenant_id, service_id, key_version)`; per‑tenant KEK is a Phase 2 opt‑in.
