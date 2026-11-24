# Proxy public egress

## Purpose

Each stored credential carries an egress scope, `any` or `public`. For a `public` credential the egress proxy connects only
to public network addresses, whatever the stored target's name resolves to when the request is made.

## ADDED Requirements

### Requirement: The vault stores an egress scope with each credential
The changelog `apps/admin-api/db/changelog/034-credential-egress-scope.yaml`, included once in
`db.changelog-master.yaml`, SHALL add to `vault.credentials` the column `egress_scope` as `TEXT NOT NULL DEFAULT 'any'`
with a CHECK that allows `any` and `public`, so every existing row is `any`. The vault gRPC calls SHALL carry the scope in
call metadata under the key `x-mintkey-egress-scope`: a `PutCredential` request names it (`any` or `public`), and every
successful `GetCredential` answers it in its response header. `VaultAdapterClient.put_credential`
(`admin_api.services.vault_client`) SHALL take a trailing parameter `egress_scope: str = ""` and, when it is not empty, send
the metadata pair; operator call sites do not pass it.

#### Scenario: the changelog adds the column
- **WHEN** the changelog file is parsed as YAML and the master changelog is read
- **THEN** the file holds an SQL change whose text contains `ALTER TABLE vault.credentials`, `ADD COLUMN egress_scope TEXT
  NOT NULL DEFAULT 'any'` and `CHECK (egress_scope IN ('any', 'public'))`, a `columnExists` precondition with
  `onFail: MARK_RAN`, and a rollback; the master has exactly one include whose file name is
  `034-credential-egress-scope.yaml`

#### Scenario: the admin-api client sends the scope
- **WHEN** `put_credential` runs against a fake stub once with `egress_scope="public"` and once without the argument
- **THEN** the `metadata` of the first `PutCredential` call holds the pair `("x-mintkey-egress-scope", "public")` besides
  the two identity pairs, and the second call's metadata holds no such pair

### Requirement: The vault adapter stores and returns the scope
`PutCredential` SHALL store the scope named in the request metadata when it is `any` or `public`; SHALL answer
`InvalidArgument` and store nothing for any other value or for more than one value; and, when no scope is named, SHALL
store the scope of the service's current credential version, or `any` when there is none. When that lookup fails for a
reason other than "no current version", the put SHALL fail and store nothing. `GetCredential` SHALL set the scope of the
version it returns in the response header, as `any` or `public`, for every authentication scheme. The SQLite, PostgreSQL
and HashiCorp stores, the DEK cache entry (`internal/cache/dek_cache.go`), `CredentialRecord` (`EgressScope`) and the two
`vault-migrate-*` commands SHALL carry the value; a HashiCorp version document without the key reads as `any`.

#### Scenario: put and get round-trip the scope
- **WHEN** credentials for services S1..S3 are put through the gRPC server of `newTestGRPCServer` with the metadata value
  `public`, `any` and no value, and read back with `GetCredential` (the response header read with `grpc.Header`)
- **THEN** the headers carry `public`, `any` and `any`

#### Scenario: a rotation keeps the scope unless it names one
- **WHEN** a credential is put with `public`, put again with no scope, read, then put with `any` and read
- **THEN** the second version reads `public` and the third reads `any`

#### Scenario: an unusable scope is refused
- **WHEN** a credential is put with the value `private`, and another with two values of the key
- **THEN** both calls fail with `InvalidArgument`, and `ListVersions` for the service lists no version

#### Scenario: a failing lookup fails the put
- **WHEN** a put names no scope and the service's store (a wrapper of the in-memory store whose `Get` returns an error that
  is not "no rows") fails the lookup of the current version
- **THEN** the call fails and the wrapped store holds no version for the service

#### Scenario: every scheme's response carries the scope
- **WHEN** a `public` credential of the schemes `api_key_header`, `bearer_token`, `apple_jwt` and `google_service_account`
  (built as the existing tests of those schemes build them) is read
- **THEN** each response header has `x-mintkey-egress-scope` equal to `public`

#### Scenario: the HashiCorp document tolerates a missing key
- **WHEN** `marshalVersionDoc` encodes a record whose scope is `public`, and `unmarshalVersionDoc` decodes the result and a
  document without the key
- **THEN** the encoded map has `egress_scope` equal to `public`, the first decode reads `public` and the second reads `any`

#### Scenario: no file that handles the stored target forgets the scope
- **WHEN** a test walks the non-test Go files of `apps/vault-adapter` and, in every file whose text mentions `target_url`
  or `TargetURL` (compared case-insensitively), looks for `egress_scope` or `EgressScope` (case-insensitively)
- **THEN** every such file mentions it, and at least eight files were found

### Requirement: The proxy refuses non-public addresses for a public credential
`vault.GetCredentialResponse` (`apps/proxy-plugin/internal/vault/client.go`) SHALL gain `EgressScope string`, read from the
`x-mintkey-egress-scope` response header (empty when the header is absent). The new package file
`apps/proxy-plugin/internal/egress/public.go` SHALL give:

```go
const ScopeAny, ScopePublic = "any", "public"
var ErrTargetNotPublic = errors.New("target address is not public")
func IsPublicIP(ip net.IP) bool
func PublicDialContext(r Resolver, d *net.Dialer) func(ctx context.Context, network, addr string) (net.Conn, error)
func NewPublicTransport() *http.Transport
type Resolver interface { LookupIPAddr(ctx context.Context, host string) ([]net.IPAddr, error) }
```

`IsPublicIP` SHALL be false for unspecified (`0.0.0.0/8`, `::`), loopback (`127.0.0.0/8`, `::1`), private (`10.0.0.0/8`,
`172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`, `fe80::/10`), carrier-grade NAT (`100.64.0.0/10`),
unique-local (`fc00::/7`), multicast (`224.0.0.0/4`, `ff00::/8`) and reserved (`240.0.0.0/4`, which holds the broadcast
address) addresses, after unwrapping an IPv4-mapped IPv6 address. The dial function SHALL resolve a host name (an IP literal
is classified as it is), SHALL return an error that wraps `ErrTargetNotPublic` when any resolved address is not public, and
otherwise SHALL connect to a resolved address it checked, never to the name. `NewPublicTransport` SHALL use that dial
function and no proxy from the environment. The proxy SHALL use that transport for every flow when the credential's
`EgressScope` is anything other than the empty string or `any` (an unknown value counts as `public`), and SHALL answer a
refused connection with 502 and the body `bad gateway: target address not allowed`.

#### Scenario: a public credential is never sent to a non-public address
- **WHEN** a credential with scope `public` and a stored target from this list is used by each of the five flows (generic,
  classical key, digest, OAuth2 client credentials and password grant, as in the tests of `proxy-stored-target`):
  an `httptest` server on `127.0.0.1`, `http://127.0.0.1:9`, `http://[::1]:9`, `http://10.1.2.3`, `http://172.16.0.9`,
  `http://192.168.1.5`, `http://169.254.169.254`, `http://100.64.0.1`, `http://100.127.255.255`, `http://[fd00::1]`,
  `http://[fe80::1]`, `http://224.0.0.1`, `http://[ff02::1]`, `http://0.0.0.0`, `http://[::]`, `http://255.255.255.255`,
  `http://240.0.0.1`, `http://[::ffff:10.0.0.1]`, `http://[::ffff:7f00:1]` and `http://localhost:<port of the server>`
- **THEN** every answer is 502 with the body `bad gateway: target address not allowed`, and the local server received no
  request

#### Scenario: the other scopes are unchanged
- **WHEN** the same local server is the stored target with scope `any` and with no scope
- **THEN** each of the five flows reaches it and returns its answer

#### Scenario: an unknown scope is treated as public
- **WHEN** the credential's scope is `bogus` and the stored target is the local server
- **THEN** the answer is 502 with the body `bad gateway: target address not allowed`

#### Scenario: the scope arrives from the vault
- **WHEN** a fake vault gRPC server answers `GetCredential` with the response header `x-mintkey-egress-scope: public` and a
  loopback target, for the generic flow and the classical-key flow
- **THEN** both answers are 502 with the body `bad gateway: target address not allowed`, and with the header value `any`
  and with no header both reach the server
