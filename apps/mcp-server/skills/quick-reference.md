# Mintkey Quick Reference

URI: `mintkey://quick-reference` · also `mintkey_bootstrap(section="quick-reference")`

## ID formats
| Prefix | Entity |
|---|---|
| `svc_<26>` | Service |
| `agent_<26>` | Agent |
| `tnt_<26>` | Tenant |
| `perm_<26>` | Permission grant |
| `sec_<26>` | Agent secret |
| `cred_<26>` | Credential record |

All 26-char suffixes are Crockford base32 (uppercase, no I/L/O/U). ULIDs, not UUIDs.

## The 3-step REST/HTTP call
```
1. mintkey_discover()  →  svc_ id, connect_type, how_to_call
2. mintkey_request_token({ service_id, action:"call" })  →  { token, expires_at }
3. GET/POST {proxy_url}/v1/call/{svc_id}/{path}  Authorization: Bearer {token}
```
Never add upstream auth — the proxy injects it silently.

## Top tool signatures
```
mintkey_discover()
mintkey_describe_service({ service_id })
mintkey_request_token({ service_id, action })  →  { token, expires_at, [ssh_connect] }
secret_put({ name, value, [content_type] })    →  { secret_id, version }
secret_get({ secret_id })                      →  { value, access }
secret_list({ [after], [limit] })              →  { secrets[], next_cursor }
secret_delete({ secret_id })
```

## connect_type routing
| `connect_type` | Where to call | Auth |
|---|---|---|
| `http` | `{proxy_url}/v1/call/{svc_id}/{path}` (Kong `:8000`) | JWT as Bearer |
| `ssh` | SSH bastion `:2222` | JWT as SSH **password** |
| `email` | `/v1/tools/email_*` REST (email-proxy `:8088`) | agent key directly |

## Errors at a glance
```
401 token_expired → request_token again
401 agent_revoked → stop; tell operator
403 permission_denied → ask operator for grant
403 constraint_violated → check your_constraints
404 unknown_service → re-discover
5xx upstream_error → retry with backoff
```

## Section aliases (mintkey_bootstrap)
| alias | Returns |
|---|---|
| `index` (default) | compact TOC |
| `auth` | authentication block |
| `discover` | service discovery block |
| `proxy_call` | proxy usage block |
| `email` | email services block |
| `secrets` | agent secrets block |
| `quick_start` | quick start block |
| `use_cases` | use cases table |
| `anti_patterns` | top 6 anti-patterns |
| `rest-api` | REST/HTTP guide (this resource: mintkey://guides/rest-api) |
| `ssh` | SSH guide (mintkey://guides/ssh) |
| `secrets-guide` | secrets guide (mintkey://guides/secrets) |
| `email-guide` | email guide (mintkey://guides/email) |
| `quick-reference` | this document (mintkey://quick-reference) |
| `full` | entire agent-bootstrap.md |

## Top 5 anti-patterns
1. Sending upstream auth header on a proxy call → it is silently stripped and replaced.
2. Calling upstream `base_url` directly → use the proxy; JWT is audience-bound to the proxy.
3. Storing operator service config in `secret_put` → use discover + request_token + proxy.
4. Hardcoding `svc_` IDs → re-discover every session; IDs live in Postgres.
5. Routing SSH/email through Kong (`:8000`) → SSH uses bastion `:2222`; email uses email-proxy `:8088`.
