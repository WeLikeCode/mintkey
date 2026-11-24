# The proxy sends a request only to the target stored with the credential

## Why

A credential is stored together with the target it is meant for (`vault.credentials.target_url`, the service's base URL at
the time the credential was stored). The egress proxy injects the credential into the upstream request, so the place the
request goes is part of what the credential is allowed to do: the proxy takes the upstream from the stored target only.

The agent-governance changes let agents register services and set credentials. Their rule that a credential is bound to its
target relies on that single source. The same change completes what the proxy sends
back: the response scrubber (`apps/proxy-plugin/internal/scrubber`) is part of the design of the proxy (ADR-0014.4) and is
now applied to every proxied response, so that a credential value an upstream repeats in its answer does not reach the
caller.

## What Changes

- A new `resolveTarget` decides the upstream for each of the five flows of `apps/proxy-plugin/cmd/proxy-plugin/main.go`
  from `vault.GetCredentialResponse.TargetURL` only. A missing, unparsable or non-http(s) target answers 502 with a text
  that names the cause. `X-Mintkey-Target` is still removed from the upstream request; `DEFAULT_TARGET` stays a parsed but
  unused setting.
- Liquibase `033-credential-target-backfill.yaml` fills every empty `vault.credentials.target_url` from the service's
  `base_url` (http and https only), so credentials stored before the target was recorded keep working.
- A new `newUpstreamProxy` builds the reverse proxy of every flow with a response scrubber and typed 502 answers.
  `scrubber.ScrubWith` adds exact-value redaction of the injected credential (raw, base64 and query-escaped forms) for every
  service, and applies the pattern rules of `Scrub` (header removals, JWT, `api_key=` and `sk_` strings) only when the new
  proxy setting `MINTKEY_PROXY_SCRUB_PATTERNS` is true (default false); `Scrub`
  keeps the part of a body that lies past its 256 KiB scan bound and keeps the length headers consistent. Event streams
  are not buffered, and responses with an encoding the proxy cannot read are refused.

## Capabilities

### New Capabilities
- `proxy-stored-target`: the target of a proxied request, the backfill of stored targets, and the scrubbing of proxied
  responses.

## Impact

- Changed: `apps/proxy-plugin/cmd/proxy-plugin/main.go` (the five flows), `apps/proxy-plugin/internal/scrubber/response.go`,
  the field `ScrubPatterns` and comments in `apps/proxy-plugin/internal/config/config.go`, a comment in
  `apps/proxy-plugin/internal/vault/client.go`, `apps/admin-api/db/changelog/db.changelog-master.yaml`.
- New: `apps/proxy-plugin/cmd/proxy-plugin/target.go`, `apps/proxy-plugin/cmd/proxy-plugin/upstream.go`,
  `apps/admin-api/db/changelog/033-credential-target-backfill.yaml`.
- New tests: `apps/proxy-plugin/internal/scrubber/response_tail_test.go`, `apps/proxy-plugin/cmd/proxy-plugin/stored_target_test.go`,
  `apps/proxy-plugin/cmd/proxy-plugin/response_scrubbing_test.go`, `apps/proxy-plugin/internal/config/scrub_patterns_test.go`,
  `tests/unit/admin_api/test_credential_target_backfill.py`.
- Changed tests (live stack, outside the gate): `tests/acceptance/test_e2e_smoke.py`, `tests/acceptance/test_golden_path.py`,
  `tests/acceptance/test_data_plane_smoke.py`, and `tests/acceptance/test_classical_key.py`: the
  mock backend echoes the credential it receives, which the proxy now redacts by exact value (design D4; the pattern rules play no part). The live tests register their
  services with `base_url` `http://mock-backend:8999`, so they use a stored target; `apps/seed-job` writes no vault rows.
- Callers: requests for credentials with a stored target behave as before, apart from the scrubbing (design D4, D5, D8). No
  test sends `X-Mintkey-Target` or relies on `DEFAULT_TARGET` (searched `apps/` and `tests/`).
- Operators: the migration needs no action. `MINTKEY_PROXY_SCRUB_PATTERNS` (proxy-plugin environment, default `false`) turns
  the pattern rules on; no deployment file sets it. Credentials in the SQLite and HashiCorp vault backends are not reached by it;
  one of them with an empty target answers 502 until its credential is stored again.
