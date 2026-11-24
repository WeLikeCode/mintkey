# The proxy connects a public credential only to public addresses

## Why

Operators register services whose targets are often inside their own network, so the proxy's default is to connect to
whatever the stored target names. Targets that an agent supplies (a later change of this plan) must be public: the name
is checked when it is stored, but a name can resolve to another address later. The check therefore has to be repeated
at the moment the proxy connects, and the credential has to say which rule applies.

This change adds that vocabulary: an egress scope stored with each credential (`any`, the value of every existing row, or
`public`), a put-time parameter that sets it, and a proxy that connects a `public` credential only to public addresses.
It depends on `proxy-stored-target`: the target comes from the credential only, and every flow builds its reverse proxy
with `newUpstreamProxy`.

## What Changes

- Liquibase `034-credential-egress-scope.yaml` adds `vault.credentials.egress_scope TEXT NOT NULL DEFAULT 'any'` with a
  CHECK of `any` and `public`.
- The scope travels in gRPC call metadata, key `x-mintkey-egress-scope`: on `PutCredential` (request) and on every
  `GetCredential` answer (response header). `vault.proto` documents it in comments; no generated stub changes (design D6).
  `VaultAdapterClient.put_credential` takes `egress_scope: str = ""`.
- The vault adapter validates and stores the scope (`any`, `public`; no value keeps the scope of the current version so a
  rotation cannot widen it; the not-found answer of every store is `sql.ErrNoRows`, wrapped; lookup and write of a service are
  serialised in the process), returns it with every credential, and carries it through the SQLite, PostgreSQL and
  HashiCorp stores, the DEK cache and the two migration commands.
- The proxy reads the header into `EgressScope`; for anything but empty or `any` it builds the flow's reverse proxy over a
  transport whose dial function refuses any non-public resolved address (`egress.NewPublicTransport`) and answers 502
  `bad gateway: target address not allowed`.

## Capabilities

### New Capabilities
- `proxy-public-egress`: the egress scope of a stored credential and the proxy's connect-time check.

## Impact

- Changed: `docs/architecture/contracts/vault-adapter/vault.proto` (comments only), `apps/admin-api/src/admin_api/services/vault_client.py`,
  `apps/admin-api/db/changelog/db.changelog-master.yaml`,
  `apps/vault-adapter/internal/{server/vault.go,server/grpc.go,cache/dek_cache.go,store/sqlite.go,store/postgres.go,store/hashicorp_doc.go}`,
  `apps/vault-adapter/cmd/vault-migrate-sqlite-to-pg/main.go`, `apps/vault-adapter/cmd/vault-migrate-pg-to-hashicorp/main.go`,
  `apps/proxy-plugin/internal/vault/client.go`, `apps/proxy-plugin/cmd/proxy-plugin/main.go`,
  `apps/proxy-plugin/cmd/proxy-plugin/upstream.go`.
- New: `apps/admin-api/db/changelog/034-credential-egress-scope.yaml`, `apps/proxy-plugin/internal/egress/public.go`.
- New tests: `tests/unit/admin_api/test_credential_egress_scope_changelog.py`, `tests/unit/admin_api/test_vault_client_put_egress_scope.py`,
  `apps/vault-adapter/internal/server/egress_scope_test.go`, `apps/vault-adapter/internal/store/egress_scope_source_test.go`,
  `apps/vault-adapter/internal/store/hashicorp_egress_scope_test.go`, `apps/proxy-plugin/cmd/proxy-plugin/public_egress_test.go`.
- Callers: no existing caller names a scope, so every credential stays `any` and nothing changes for operators.
- Operators: run the migration before the new vault adapter starts (the adapter's PostgreSQL queries name the column).
- Depends on: `proxy-stored-target`. Used by: `agent-service-publishing`, which passes `public` for agent-owned services.
