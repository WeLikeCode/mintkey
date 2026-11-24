# Design: proxy-public-egress

## Context

The vault adapter (`apps/vault-adapter`) keeps one row per credential version in `vault.credentials` (PostgreSQL;
SQLite and HashiCorp stores mirror the columns). `PutCredential` in `internal/server/grpc.go` builds `PutCredentialArgs`
(`internal/server/vault.go`) and `VaultService.PutCredential` writes a `store.CredentialRecord`; `GetCredential` returns the
fields in a `GetCredentialResult` that the eight response constructors of `GetCredential` (`grpc.go`) copy into
`vaultv1.GetCredentialResponse`. `internal/cache/dek_cache.go` caches `(wrappedDEK, encPayload, TargetURL, ...)` per
`(tenant, service, version)`. `hashicorp_doc.go` marshals a record to a flat map, and `unmarshalVersionDoc` requires every
string key it reads. Two commands copy rows between stores by naming columns (`cmd/vault-migrate-sqlite-to-pg`,
`cmd/vault-migrate-pg-to-hashicorp`). The adapter already reads call metadata (`x-mintkey-service-identity`,
`x-mintkey-service-token`) in its scope interceptor, and the admin-api client sends the same two pairs on every call.

The proxy (`apps/proxy-plugin`) builds its reverse proxy in five flows; after `proxy-stored-target` each calls
`h.newUpstreamProxy(target, base, injected...)` and the digest flow builds `credential.NewDigestTransport(payload, base)`.
`internal/credential/ssrf.go` holds the dial-time guard of the OAuth2 token exchanges; it keeps its own ranges and behaviour.
The new guard is separate (`internal/egress`): it checks the ranges of this spec, including carrier-grade NAT, and dials the
address it checked.

The admin-api client is `VaultAdapterClient.put_credential` in `apps/admin-api/src/admin_api/services/vault_client.py`.

## Interfaces

Given to later changes: the column `vault.credentials.egress_scope`; `put_credential(..., egress_scope: str = "")` (the
value `public` makes the stored credential connect-checked; the empty value keeps the current version's scope); the metadata
key `x-mintkey-egress-scope` on `PutCredential` and `GetCredential`; and on the proxy `egress.IsPublicIP`,
`egress.PublicDialContext`, `egress.NewPublicTransport`, `egress.ErrTargetNotPublic` and
`(*proxyHandler).egressBase(scope string, base http.RoundTripper) http.RoundTripper` (returns `base` for `""` and `any`, the
handler's shared public transport otherwise).

```go
// egress/public.go
func PublicDialContext(r Resolver, d *net.Dialer) func(ctx context.Context, network, addr string) (net.Conn, error)
// splits addr; an IP literal is classified directly, a name is resolved with r (net.DefaultResolver when nil); an empty
// answer is an error; any non-public address returns fmt.Errorf("%w: %s resolves to %s", ErrTargetNotPublic, host, ip);
// otherwise it dials net.JoinHostPort(ip.String(), port) for each checked address in order and returns the first success.
func NewPublicTransport() *http.Transport // a clone of http.DefaultTransport with Proxy nil and that DialContext

// vault adapter, internal/server/grpc.go
const egressScopeMetadataKey = "x-mintkey-egress-scope"
// PutCredential: md, _ := metadata.FromIncomingContext(ctx); md.Get(egressScopeMetadataKey)  // none, one, or many
// GetCredential: grpc.SetHeader(ctx, metadata.Pairs(egressScopeMetadataKey, result.EgressScope)) once, after the lookup
// proxy client, internal/vault/client.go: call option grpc.Header(&md); EgressScope = first value of md.Get(key), or ""
```

`newProxyHandler` creates one `publicTransport` (connection pooling) and `egressBase` returns it. The `ErrorHandler` of
`newUpstreamProxy` maps `errors.Is(err, egress.ErrTargetNotPublic)` to the 502 text of the spec.

## Decisions

**D1. A put that names no scope keeps the current version's scope.** `VaultService.PutCredential` with no scope reads the
current version's record (`store.Backend.Get` with version 0) and reuses its scope (`any` when the store reports no such
row: an error satisfying `errors.Is(err, sql.ErrNoRows)`, or a `(nil, nil)` result. The three stores all wrap
`sql.ErrNoRows` today: SQLite in `Get`, PostgreSQL after `pgx.ErrNoRows` and HashiCorp for an empty index, a missing
version document and `ErrSecretNotFound`; a store that signals absence another way must map it to that sentinel). Lookup and
write run under one mutex per `(tenant, service)`, so a put that names no scope cannot overwrite the scope a concurrent
put has just set; the adapter is a single instance (`deploy/helm/mintkey/templates/stateful/vault-adapter.yaml` sets
`replicas: 1`), and a second instance would need a database-level lock, which this change does not add. A rotation by an operator (`rotate_credential` calls `put_credential` without the argument) therefore cannot turn a
`public` credential into `any`. A lookup that fails for another reason fails the put, so a store error never stores `any`.
Naming `any` or `public` sets it. The rule lives once, in the service, for all stores.

**D2. Unknown values fail closed in the proxy.** The adapter stores only `any` and `public`, but the proxy treats every
value other than empty and `any` as `public`, so an extra scope of a newer adapter can only make connections stricter. The
empty value is what an older adapter gives, and means `any`.

**D3. The checked address is the connected address.** Resolving, checking and then dialling the name would let a second
lookup return another address. The dial function dials the checked IP literal; TLS still validates the certificate against
the URL's host name, because `http.Transport` takes the server name from the URL, not from the dial address.

**D4. Ranges.** Those of the spec: unspecified (`0.0.0.0/8`, `::`), loopback, private, link-local, carrier-grade NAT,
unique-local and multicast addresses plus the reserved block `240.0.0.0/4`, with IPv4-mapped addresses unwrapped first.
Everything else counts as public, including documentation and benchmarking ranges. The store-time rule of
`agent-service-publishing` (`mintkey_models.egress.address_is_public`, which accepts global unicast addresses only) is
deliberately stricter: it also refuses those documentation and benchmarking ranges and the other special-purpose blocks,
and `agent-service-publishing` applies it to every name an agent supplies. The two rules differ in the safe direction: the
connect-time check refuses nothing that the store-time check accepted, and it is the one that applies to a name whose
address changes after it was stored.

**D5. No environment proxy.** `NewPublicTransport` sets `Proxy` to nil so `HTTP_PROXY` cannot move the connection to an
address the guard never sees. Redirects are not followed (a reverse proxy returns them to the caller), so each connection
is made for the stored target.

**D6. The scope travels in call metadata, not in new message fields.** The generated stubs (`packages/go/vault/v1`,
`apps/admin-api/src/admin_api/services/vault_pb2.py`, the MCP copy) are checked in, were produced by different protoc
versions (the Go header records protoc 34.1, the Python one 31.1), and the L4 gate has no protoc: a unit that must add proto
fields cannot regenerate them. Metadata needs no stub change: the adapter and the proxy use `metadata` and `grpc.Header`,
the admin-api client one more tuple, and the metadata key is documented in the comments of `vault.proto` (comment-only
edit; no generated file changes meaning). The alternative, `string egress_scope = 12;` in `PutCredentialRequest` and `= 18;` in
`GetCredentialResponse` with stubs regenerated by a person before the plan runs, changes only how the value is carried; the
adapter and proxy scenarios stay the same.

**D7. Tests of the PostgreSQL and HashiCorp stores.** Their live tests need Docker or a server and are not part of the gate.
The gate decides the store behaviour through the SQLite store (same `store.Backend` contract, through the gRPC server),
the HashiCorp document functions, and a source test that every file handling `target_url` also handles the scope.

**D8. OAuth2 token exchanges keep their own guard.** The connect-time check wraps the transport of the upstream request. The
token endpoint of the two OAuth2 flows comes from the credential payload and is called through `credential/ssrf.go`
(`NewTokenExchanger`), which stays as it is, with its own ranges. In this plan only operators store an OAuth2 credential,
which is `any`: `agent-service-publishing` accepts no OAuth2 scheme from an agent, so no `public` credential reaches an
exchange. A later change that lets an agent store one must also route its exchange through `egress.NewPublicTransport`.

**D9. Test support lives in the unit's own file.** `public_egress_test.go` defines `startScopedFakeVault(t, resp
*vaultv1.GetCredentialResponse, scope string) *vault.Client` (a gRPC server over `UnimplementedVaultAdapterServer` whose
`GetCredential` calls `grpc.SetHeader(ctx, metadata.Pairs("x-mintkey-egress-scope", scope))` when `scope` is not empty and
returns `proto.Clone(resp)`) and `scopedFlows(t, h, target, scope)`, which builds the five calls as `callFlows` does but with
that fake vault and, for the direct calls, the scope set by reflection. It calls `countingUpstream` of `stored_target_test.go`
and edits no other test file.

## Risks and edge cases

- A name that resolves to several addresses is refused when any one is non-public.
- The first request of a `public` credential pays one DNS lookup per new connection; pooled connections are reused.
- Mid-rollout: an old adapter returns no header (the proxy reads `any`); a new adapter before the migration fails on its
  queries, so the migration is applied first.
- The classification of the public side (an address just outside a refused range) is not tested against a live network;
  the tests cover each refused range, IPv4 and IPv6, through the proxy.
- A client that does not send the metadata (an older admin-api) stores the current scope, which for a new service is `any`.

## Follow-ups

- A fetch-time egress re-check in `get_openapi`, which fetches an OpenAPI document from a service-supplied URL.
