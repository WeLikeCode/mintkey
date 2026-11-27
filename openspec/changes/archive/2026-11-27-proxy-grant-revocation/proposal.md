# A revoked grant's tokens stop working at once

## Why

A token is a signed statement that an agent may call a service, issued from a grant and valid for up to an hour. When an
operator or an agent revokes the grant, admin-api publishes the change event `agent.permission.revoked` (from
`revoke_permission` and from the grant write path of `grant-expiry`). The agent-governance changes let agents grant and
revoke access to each other, so a revoked grant's tokens have to stop working at the egress proxy at once; the proxy
therefore acts on that event.

## What Changes

- The subscriber (`apps/proxy-plugin/internal/changes/subscriber.go`) handles `agent.permission.revoked` and records the
  (agent, service, `revoked_at`) triple in a new `revocation.GrantRevocationSet`, for 3630 seconds from `revoked_at`.
- `ServeHTTP` refuses with 401 `unauthorized: token revoked` a token of a recorded pair whose `iat` is at or before the
  revocation second (or is missing). Tokens issued after a later grant carry a later `iat` and work.
- The handler owns the set, and `changesSubscriber` hands it to the subscriber, like the existing agent and token sets.
- The broker already signs `iat` (Unix seconds) into every token (`Issue` in `apps/broker/internal/issuer/issuer.go`, covered
  by `TestIssuedJWT_HasCorrectClaims`); no broker change is needed.

## Capabilities

### Modified Capabilities
- `proxy-token-revocation`: gains the grant-revocation requirement (ADDED requirement in this change's delta spec).

## Impact

- Changed: `apps/proxy-plugin/internal/changes/subscriber.go`, `apps/proxy-plugin/cmd/proxy-plugin/main.go`
  (`proxyHandler`, `newProxyHandler`, `changesSubscriber`, `ServeHTTP`).
- New: `apps/proxy-plugin/internal/revocation/grant_set.go`.
- New tests: `apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go`,
  `apps/proxy-plugin/internal/changes/subscriber_grant_revoked_test.go`.
- Callers: tokens of pairs that have no recorded revocation are unaffected, and so are the other revocation events.
  A revocation takes effect when the proxy receives the event, which is the change channel's delivery time.
- Depends on: `grant-expiry` (its `revoke_permission` NOTIFY payload with `service_id` and `revoked_at`) and
  `proxy-public-egress` (both edit `proxyHandler`, `newProxyHandler` and `ServeHTTP` of `apps/proxy-plugin/cmd/proxy-plugin/main.go`).
- Out of scope: revocation in the SSH proxy and email proxy, and per-action revocation (design.md).
