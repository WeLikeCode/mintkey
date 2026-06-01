# ADR-0023: SSH upstream addressing — services.base_url is canonical

## Status

Accepted — 2026-06-01.

Amends [ADR-0022](0022-ssh-bastion.md) §D2: the `target_address` column in `vault.credentials` is
deprecated for SSH routing. `services.base_url` is the sole source of truth for the upstream
host:port. `target_address` is left in place as a transition safety net; planned removal in a
follow-up migration (see §Follow-up F2).

---

## Context

ADR-0022 §D2 shipped `vault.credentials` with a `target_address` column (format: `host:port`) that
the ssh-proxy read on every `GetCredential` gRPC call to determine where to dial. The column was
populated at credential-creation time by the operator.

`services.base_url` (e.g. `ssh://internal-server.corp:22`) existed in the `public.services` table
from the original admin-api design and was the field operators edited via the Admin UI **Service**
form. These two columns represented the same information via different paths:

1. An operator creates a service → sets `base_url` in the service form.
2. The same operator (or a different operator) creates a credential for that service → sets
   `target_address` in the credential form.

The two columns **drifted**: editing `base_url` on the service did **not** propagate to
`target_address` on the credential. The symptom: an operator changes a service from
`ssh://ssh-target:2222` to `ssh://172.24.1.234:22` in the Admin UI, saves the service, but the
ssh-proxy keeps dialling `ssh-target:2222` (the stale value in `vault.credentials.target_address`).

Chunk C-6 of the remediation added a cascade — the admin-api updates `target_address` on the
credential row whenever `services.base_url` changes. This is a defensive safeguard that keeps the
columns in sync until `target_address` is removed, but it does not resolve the underlying
redundancy.

Chunk C-7 extended the vault-adapter's `GetCredential` gRPC handler to LEFT JOIN
`public.services` and return `base_url` alongside the credential row. The ssh-proxy was updated to
parse `base_url` (stripping the `ssh://` scheme prefix) and use it as the dial target for all SSH
auth schemes (`ssh_password`, `ssh_private_key`, `ssh_ca`). It falls back to `target_address` only
when `base_url` is absent — a safety net for rows that pre-date C-7 or that were not touched by
the C-6 cascade.

---

## Decision

**`services.base_url` is the sole source of truth for SSH upstream host:port.**

Specifically:

1. **vault-adapter `GetCredential`** performs a LEFT JOIN on `public.services` using
   `(tenant_id, service_id)` and includes `base_url` in the returned `vault.Credential` struct.
   The JOIN uses the `mintkey_migrate` role, which bypasses RLS on `public.services`; see
   §Consequences for the RLS note.

2. **ssh-proxy** reads `base_url` for all SSH auth schemes. The `ssh://` scheme prefix is stripped;
   IPv6 literals are unwrapped from brackets (e.g. `ssh://[::1]:22` → `[::1]:22` for `net.Dial`).
   The fallback to `target_address` is retained as a transition safety net.

3. **`ssh_user`** remains per-credential — it is auth material, not routing. The credential row
   continues to carry it.

4. **`vault.credentials.target_address`** is left in the schema. The C-6 cascade (admin-api
   writes `target_address` when `base_url` changes) continues to run — no harm, keeps the column
   in sync with `base_url` until it is dropped.

5. **Credential registration** requires only auth material. For SSH services, operators set the
   upstream host:port once in the service's `base_url`. The credential form should only ask for
   auth material: private key PEM, password, or CA key, plus `ssh_user`.

---

## Consequences

### Positive

- **No more drift.** Editing `services.base_url` in the Admin UI takes effect after the next
  `GetCredential` call (subject to DEKCache TTL, ≤ 10 min by default). A single field owns the
  routing address.
- **Simpler credential registration.** Operators no longer need to enter `target_address` when
  registering an SSH credential. The credential holds only auth material.
- **Consistent with the general Mintkey model.** `services.base_url` is already the routing
  address for HTTP services (used by Kong-syncer to configure upstream routes). SSH services now
  follow the same pattern.
- **The C-6 cascade still runs.** Existing rows in `vault.credentials.target_address` are
  kept in sync with `base_url` through cascade until the column is removed (F2).

### Costs and risks

- **DEKCache lag.** Routing changes do not take effect immediately — they are visible after the
  next `GetCredential` call lands (cache TTL ≤ 10 min). Operators expecting instant propagation
  should be aware of this window. Follow-up F1 tracks cache invalidation on `base_url` change.
- **RLS on `public.services` JOIN.** The vault-adapter currently runs the `public.services` JOIN
  as `mintkey_migrate` (the migration/superuser role), which bypasses RLS. This is acceptable
  for Phase 1 because vault-adapter already authenticates callers via the service-identity boot
  secret and is not a multi-tenant HTTP endpoint. If vault-adapter is ever moved to
  `mintkey_app` (the RLS-subject role), the JOIN requires
  `set_config('app.current_tenant', ...)` to be set before the query to remain tenant-safe.
  Tracked as follow-up F3.
- **`target_address` still in the schema.** The column and the C-6 cascade constitute dead code
  for new credentials. This is deliberate: removing the column before a quiet observation period
  would be risky. Follow-up F2 schedules the drop.

---

## Follow-up

| ID | Description |
|---|---|
| F1 | Emit a synthetic `credential.rotated` (or a new `service.base_url_changed`) event when `services.base_url` changes, so the vault-adapter DEKCache is invalidated promptly. |
| F2 | Migration to `DROP COLUMN vault.credentials.target_address` (and remove the corresponding field from vault.proto and the C-6 cascade logic) after a quiet observation period on the `fix/ssh-credential-flow` branch merged to main. |
| F3 | If vault-adapter ever moves to `mintkey_app` role for the `public.services` JOIN, add `set_config('app.current_tenant', ...)` before the query for RLS safety. |
| F4 | Admin UI credential form: hide the `target_address` field for `ssh_password`, `ssh_private_key`, and `ssh_ca` auth schemes. Currently it is still shown (per C-1 work); the field is now dead UI for SSH services. |

---

## References

- [ADR-0022](0022-ssh-bastion.md) — SSH bastion routing model. Corrigendum: `target_address` is
  deprecated for SSH routing per this ADR; `base_url` takes authority.
- [ADR-0021](0021-vault-storage-backend-postgres.md) — defines the `vault.credentials` schema.
  Corrigendum: `target_address` column is deprecated for SSH services per this ADR.
- Remediation `remediation/active/2026-06-01-ssh-credential-flow/` — chunks C-6 (cascade) and
  C-7 (vault-adapter JOIN + ssh-proxy reads base_url) are the implementation evidence.
- PR: TBD (opened after this branch merges).
