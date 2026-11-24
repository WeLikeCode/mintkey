# Tasks: proxy-public-egress

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Go tasks: the red step
keeps only test files, so the Go tests use only identifiers that exist before the change (the gRPC client and server, call
metadata, `ServeHTTP` and the `handle*` methods); a struct field the change adds is reached through reflection
(`reflect.Value.FieldByName`), and the test `t.Fatal`s with a message naming what is missing. Run `go test ./... -short`,
`go vet ./...` and `golangci-lint run` in each Go module touched, and `ruff check src/` and `mypy --strict src/admin_api/`
in `apps/admin-api`.

## 1. The column

- [ ] 1.1 Tests first, new file `tests/unit/admin_api/test_credential_egress_scope_changelog.py` (header and `REPO_ROOT` as
  `tests/unit/admin_api/test_notify_event_type.py`): `test_changelog_adds_the_egress_scope_column` covers the scenario "the
  changelog adds the column": it loads `apps/admin-api/db/changelog/034-credential-egress-scope.yaml`, normalises the text
  of its SQL change and asserts the three substrings of the scenario (lower-cased, whitespace collapsed), the precondition (`onFail: MARK_RAN`, `not` of
  `columnExists` with `schemaName` `vault`, `tableName` `credentials`, `columnName` `egress_scope`) and a `rollback` (`DROP COLUMN IF EXISTS egress_scope`), and exactly one include of
  that file name in `db.changelog-master.yaml`, at any position. It stays red until the file exists.
  Then create the changelog (change set `034-credential-egress-scope-1`, author `mintkey`, `splitStatements: false`) and
  its include in `apps/admin-api/db/changelog/db.changelog-master.yaml`.

## 2. The admin-api client sends the scope

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_vault_client_put_egress_scope.py` (header as
  `test_vault_client_get_credential.py`): `test_put_credential_sends_the_scope_metadata` covers "the admin-api client sends
  the scope" with a `MagicMock` stub whose `PutCredential` is an `AsyncMock` returning `MagicMock(key_version=1)`, installed
  with `patch.object(client, "_stub", ...)`; it calls `put_credential` once with `egress_scope="public"` and once without the
  argument and asserts `stub.PutCredential.call_args.kwargs["metadata"]`. It stays red until the parameter exists.
  Then add `egress_scope: str = ""` as the last parameter of `VaultAdapterClient.put_credential`
  (`apps/admin-api/src/admin_api/services/vault_client.py`), appending `("x-mintkey-egress-scope", egress_scope)` to the
  metadata tuple when it is not empty (a module constant `EGRESS_SCOPE_METADATA_KEY`), with a docstring naming the two
  values; and document the metadata key in the comments of the `PutCredential` and `GetCredential` rpcs of
  `docs/architecture/contracts/vault-adapter/vault.proto` (comments only: no field, no regeneration).

## 3. The vault adapter stores and returns the scope

- [ ] 3.1 Tests first (all in `apps/vault-adapter`). New file `internal/server/egress_scope_test.go` (package `server`,
  using `newTestGRPCServer` of `grpc_test.go`; the scope goes out with `metadata.AppendToOutgoingContext` and comes back
  with the call option `grpc.Header(&md)`): `TestEgressScopeRoundTrip`, `TestEgressScopeRotationKeepsScope`,
  `TestEgressScopeUnusableValueRefused`, `TestEgressScopeFailingLookupFailsPut` (the server is built as `newTestGRPCServer`
  does, over a wrapper struct that embeds the `store.Backend` and overrides `Get` to return `errors.New("lookup failed")`)
  and `TestEgressScopeEverySchemeResponse`, `TestEgressScopeFirstPutAndConcurrentPuts` ("a first put and concurrent puts": the wrappers
  override `Get`) and `TestStoreNotFoundIsSqlErrNoRows` ("the not-found answers of the stores wrap one sentinel") cover the scenarios of the same names (`TestStoreNotFoundIsSqlErrNoRows` lives in `egress_scope_source_test.go`; `TestEgressScopeEverySchemeResponse` builds the apple_jwt and
  google_service_account credentials as `TestGRPCAppleJWT_HappyPath` and `grpc_google_service_account_test.go` do). New
  file `internal/store/hashicorp_egress_scope_test.go` (package `store`): `TestHashicorpDocEgressScope` covers "the
  HashiCorp document tolerates a missing key", setting `EgressScope` on the record with `reflect`. New file
  `internal/store/egress_scope_source_test.go` (package `store`): `TestEveryTargetURLFileHandlesEgressScope` covers "no file
  that handles the stored target forgets the scope", walking `../..` with `filepath.WalkDir`, skipping `_test.go` files, and asserting that the eight files of the scenario are among
  those found. They stay red until the adapter reads and returns the scope.
  Then: add `EgressScope string` to `store.CredentialRecord`, `PutCredentialArgs`, `GetCredentialResult` and the DEK cache
  entry; in the gRPC `PutCredential` read the metadata (`InvalidArgument` for a value other than `any` and `public`
  and for more than one value) and pass it in the args; in `VaultService.PutCredential` resolve an empty scope as design
  D1 says (`any` when the error satisfies `errors.Is(err, sql.ErrNoRows)` or the result is `(nil, nil)`; a failed put for any other
  error; the lookup and the write under one mutex per tenant and service, in a `sync.Map` of mutexes on `VaultService`); in the gRPC `GetCredential`
  set the response header once (`grpc.SetHeader`) from the result; add the column to the SQLite schema and its `migrations`
  list (`ALTER TABLE credentials ADD COLUMN egress_scope TEXT NOT NULL DEFAULT 'any'`), to the PostgreSQL `Put` INSERT, the
  `Get` column list and `scanPgRecord`, to `marshalVersionDoc` and `unmarshalVersionDoc` (a missing key is `any`, never an
  error), and to the SELECT and INSERT of both `cmd/vault-migrate-*` commands (the source value is copied; a source without
  the column copies `any`).

## 4. The proxy refuses non-public addresses

- [ ] 4.1 Tests first, new file `apps/proxy-plugin/cmd/proxy-plugin/public_egress_test.go` (package `main`). It defines its own helpers, as design D9 says: `startScopedFakeVault(t, resp, scope)`, whose
  `GetCredential` sets the response header with `grpc.SetHeader(ctx, metadata.Pairs("x-mintkey-egress-scope", scope))` when
  `scope` is not empty, and `scopedFlows(t, h, target, scope)`, which copies the setup of `callFlows` in
  `stored_target_test.go` (generic and classical-key flows through the scoped fake vault; for the three direct `handle*`
  calls the scope is set on `vault.GetCredentialResponse` with `reflect.ValueOf(credResp).Elem().FieldByName("EgressScope")`).
  It calls `countingUpstream` of that file and never edits `stored_target_test.go` or any other existing test file.
  `TestPublicScopeRefusesNonPublicTargets` covers "a public credential is never sent to a non-public address" for every
  target of the scenario in every flow; `TestOtherScopesAreUnchanged` covers "the other scopes are unchanged";
  `TestUnknownScopeIsTreatedAsPublic` covers "an unknown scope is treated as public"; `TestScopeArrivesFromVault` covers
  "the scope arrives from the vault". They stay red until the proxy reads the scope and guards the connection.
  Then create `apps/proxy-plugin/internal/egress/public.go` as the spec and design.md give it (the ranges as `net.IPNet`
  values parsed once; `IsPublicIP` unwraps `To4()` first); add `EgressScope string` to `vault.GetCredentialResponse`,
  filled from the response header through the call option `grpc.Header(&md)` in `GetCredential` of
  `apps/proxy-plugin/internal/vault/client.go`; add the handler field `publicTransport http.RoundTripper` (created in
  `newProxyHandler` with `egress.NewPublicTransport()`) and `egressBase`; in the five flows pass
  `h.egressBase(credResp.EgressScope, nil)` as `base` of `newUpstreamProxy` and to `credential.NewDigestTransport`; and
  extend the `ErrorHandler` of `newUpstreamProxy` in `apps/proxy-plugin/cmd/proxy-plugin/upstream.go` with the
  `ErrTargetNotPublic` case (the `proxy-stored-target` texts are otherwise unchanged).
