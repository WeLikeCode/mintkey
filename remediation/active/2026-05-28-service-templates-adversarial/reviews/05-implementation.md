# Implementation-Quality Adversarial Review — `feature/service-templates` (828bd7c)

Reviewer role: implementation-quality adversary (language-level + logic bugs across Go / Python / TS).
Scope note: SSRF/secrets, data-races/expiry-math, and spec-deviation are owned by other reviewers (01-security, 02-concurrency, 03-contract). This report focuses on ordinary implementation/logic bugs. Where a finding overlaps, it is flagged and kept only because the concrete mechanism is an implementation bug.

Severity counts:
- CRITICAL: 1
- HIGH: 3
- MEDIUM: 5
- LOW: 4

---

## GO

### CONFIRMED

#### [SEV: CRITICAL] [confidence: CONFIRMED] Vault scope interceptor denies every GetCredential/PutCredential in production
`apps/vault-adapter/internal/server/grpc.go:62-95`, `:99-104`; `apps/proxy-plugin/cmd/proxy-plugin/main.go:79`; `apps/proxy-plugin/internal/vault/client.go:94`.

The newly-added `scopeInterceptor` enforces `vault.read`/`vault.put` on `GetCredential`/`PutCredential`. It resolves the caller identity via `extractIdentityID(md)`, which reads the `x-mintkey-service-identity` metadata header and **returns `""` when that header is absent** (grpc.go:99-104). The proxy's vault client (`client.go:94`) only ever attaches `x-mintkey-service-token` — it never sends `x-mintkey-service-identity`. Worse, `main.go:79` constructs the client with an **empty** service token: `vault.NewClient(cfg.VaultAddrGRPC, "")`.

Consequence in production (`ListenAndServe` registers `grpc.UnaryInterceptor(scopeInterceptor(svc))`, grpc.go:222-224):
- `tokens := md.Get("x-mintkey-service-token")` is `[""]` → the `len==0 || tokens[0]==""` guard (grpc.go:80-82) fires → **every** `GetCredential` returns `PERMISSION_DENIED "missing service token"`.
- Even if a token were set, `extractIdentityID` returns `""`, so `ValidateServiceIdentity(ctx, "", token)` looks up `v.identities[""]`, never found (vault.go:430-436) → `(nil, false)` → `PERMISSION_DENIED "invalid service token"`.

Either way the entire proxy credential-fetch path (classic key path AND the new OAuth2 password-grant path) is broken once this interceptor is live. The proxy's `GetCredential` error handler (main.go:319-326) maps this to HTTP 502 for all proxied traffic.

Why it slipped: the gRPC handler tests construct the server **without** the interceptor — `grpc_test.go:44` does `srv := grpc.NewServer()` with no `UnaryInterceptor`. So `Requirement 22.5` scope enforcement is exercised by zero tests against the production wiring, and the deny-by-default failure is invisible to CI.

Impact: total proxy outage if shipped; the OAuth2 password-grant feature (and all existing credential injection) cannot fetch credentials.
Fix: have the proxy send `x-mintkey-service-identity` (and a non-empty service token) on the gRPC call, OR derive identity from the token alone in `ValidateServiceIdentity`; and add an integration test that registers the server *with* `scopeInterceptor` and asserts a valid identity/token succeeds and an empty one is denied.

#### [SEV: HIGH] [confidence: CONFIRMED] `audit.Emitter.EmitTokenExchanged` / `EmitHit` are dead code; the live audit path drops `agent_id` and does no host-redaction guarantee
`apps/proxy-plugin/internal/audit/emitter.go:91-212` (defined, only referenced by `emitter_test.go`); live path `apps/proxy-plugin/cmd/proxy-plugin/main.go:457-471`.

The carefully-written `EmitTokenExchanged` (with `TokenExchangedEvent`, host-only redaction docs, OTel span, 1s timeout) is never invoked from `main.go`. Grep shows the only non-test callers of `EmitHit`/`EmitTokenExchanged` are the unit tests. The actual handler emits a hand-built `auditq.Event` instead (main.go:458-470).

In that hand-built event the payload is `{token_url_host, success, latency_ms}` — `agent_id` is set as the envelope `ActorID`, not in the payload. `TokenExchangedEvent`/design §6 and Requirement 22.1 specify `agent_id` as a payload field. More importantly, the `Emitter` abstraction that encodes the security invariants (host-only redaction, no token, no creds) is bypassed entirely, so those invariants are not centrally enforced; any future edit to the inline `Payload` map in main.go has no guardrail.

Impact: schema drift between the documented `token.exchanged` event and what is emitted; the redaction-bearing emitter is unused, so the "host only" guarantee depends on `egress.extractHost` being correct in the orchestrator rather than the emitter. Two parallel, divergent implementations of the same event.
Fix: either delete the unused `Emitter.EmitTokenExchanged`/`EmitHit` (and `TokenExchangedEvent`) or route `main.go` through it; align the payload field set with `TokenExchangedEvent`.

#### [SEV: MEDIUM] [confidence: CONFIRMED] Duplicate, divergent `extractHost`/`ExtractHost` implementations
`apps/proxy-plugin/internal/egress/oauth2_handler.go:155-168` vs `apps/proxy-plugin/internal/audit/emitter.go:220-226`.

Two host-extraction helpers exist with different contracts: the egress one returns `"unknown"` on parse failure / empty host; the audit one returns `""`. The live path uses the egress version (`oauth2_handler.go:85`), while the dead `Emitter` uses its own. On an unpar. `url.Parse` rarely errors for these inputs, but for a malformed `token_url` the audit event would carry the literal string `"unknown"` as a hostname. Low real-world blast radius, but it is a maintenance hazard and a symptom of the dead-code split above.
Fix: collapse to one helper.

#### [SEV: MEDIUM] [confidence: CONFIRMED] `extractJSONPath` only supports nested objects — no array indexing, silent numeric-token coercion
`apps/proxy-plugin/internal/credential/exchanger.go:155-200`.

The function is documented as "JSONPath" and the design (Property 5) says "any valid JSONPath expression pointing to a string value". The implementation only walks `map[string]any` segments split on `.` — any array index (`$.data[0].token`), bracket notation, or filter is unsupported and will fail with `expected object at segment`. That is a functional limitation but acceptable if documented; the concrete *bug* is the numeric branch at :194-196: `case float64: return fmt.Sprintf("%v", v)`. A large numeric token (e.g. a 64-bit integer token) is decoded by `encoding/json` into `float64` and `%v` will render it in scientific notation (`1.234e+18`) and/or lose precision — producing a corrupted token silently injected as `Bearer`.
Impact: corrupted bearer tokens for any token endpoint that returns the token as a JSON number; broken upstream auth with no error surfaced.
Fix: use `json.Number` (decode with `UseNumber()`) for the numeric case, or reject numeric tokens outright (tokens are strings per spec).

#### [SEV: MEDIUM] [confidence: CONFIRMED] `extractExpiresIn` in exchanger is computed but never used; expiry is recomputed in the cache
`apps/proxy-plugin/internal/credential/exchanger.go:138, 204-225`; consumer `apps/proxy-plugin/internal/egress/oauth2_handler.go:146`.

`Exchange` populates `ExchangeResult.ExpiresIn` (exchanger.go:138/204-225), but the orchestrator never reads it — it calls `cache.DetermineExpiry(token, RawBody)` (oauth2_handler.go:146), which re-parses `expires_in` out of `RawBody` via `extractExpiresInFromBody` (token_cache.go:180-207). So there are two independent `expires_in` parsers and the exchanger's is pure dead work. Not a behavior bug today, but it is duplicated logic that can drift (e.g. one handles `json.Number`, both currently do, but a future edit to one won't propagate).
Fix: drop `ExpiresIn` from `ExchangeResult` (and `extractExpiresIn`) or have `DetermineExpiry` accept it instead of re-parsing.

### SUSPECTED

#### [SEV: MEDIUM] [confidence: SUSPECTED] `credential_fields` typed as `map[string]string` will reject non-string JSON body values
`apps/proxy-plugin/internal/credential/types.go:12` (`CredentialFields map[string]string`); marshalled at `exchanger.go:90`.

The stored payload is unmarshalled into `map[string]string`. Many token endpoints expect non-string body fields (e.g. `"expires_in_requested": 3600`, booleans, or `scope` arrays). If an operator stores such a value, `json.Unmarshal` of the vault payload into `OAuth2PasswordGrantCredential` fails (`cannot unmarshal number into Go value of type string`), and `HandleOAuth2PasswordGrant` returns a generic parse error → 502 with no actionable code. Requirement 19.5 emphasizes "arbitrary field names" but the values are constrained to strings on both Python (`dict[str, str]`) and Go sides, so this is internally consistent — flagging as SUSPECTED because it may be an intentional constraint, but it will surprise operators whose token endpoint needs a non-string field.
Fix: if non-string values must be supported, use `map[string]json.RawMessage` or `map[string]any`; otherwise document the string-only constraint.

#### [SEV: LOW] [confidence: SUSPECTED] `Exchange` classifies *all* `httpClient.Do` errors as `ErrTokenEndpointUnreachable`, including context-cancel / non-network
`apps/proxy-plugin/internal/credential/exchanger.go:110-117`.

The `if isNetworkError(err)` branch and the `else` branch return the **same** wrapped error (`ErrTokenEndpointUnreachable`), so `isNetworkError` is pointless here — every transport error maps to `token_endpoint_unreachable`. A context-deadline-exceeded from the *caller's* request context (not the 10s client timeout) would also be reported as "unreachable". Minor; the mapping is mostly fine because both map to 502, but the dead `isNetworkError` call is misleading.
Fix: remove the redundant branch or differentiate (e.g. timeout vs DNS) if the audit code needs it.

#### [SEV: LOW] [confidence: SUSPECTED] OAuth2 password-grant ignores `credResp.TargetURL` host-binding that the non-OAuth path also lacks
`apps/proxy-plugin/cmd/proxy-plugin/main.go:484-502`.

The OAuth2 handler builds the reverse proxy to `credResp.TargetURL` (or `X-Mintkey-Target`/default). Same pattern as the non-OAuth path; the `X-Mintkey-Target` header fallback is attacker-influenceable when no vault TargetURL is set. This is the existing proxy behavior copied verbatim, so not new, but it is now reachable via auth_scheme=8. Likely owned by security reviewer; noting the copy-paste.

---

## PYTHON

### CONFIRMED

#### [SEV: HIGH] [confidence: CONFIRMED] `OAuth2PasswordGrantPayload` validation is defined but never wired into any registration path
`apps/admin-api/src/admin_api/services/credential_service.py:103-156` (defined); no importer.

Grep across `apps/admin-api/src` and `apps/admin-api/tests` shows `OAuth2PasswordGrantPayload` and `validate_token_url_ssrf` are imported/used **nowhere** outside `credential_service.py` itself. The service-registration endpoints (`create_service`, `create_service_from_template` in `api/services.py`) accept `auth_scheme`/`auth_type` as a free `str` (`ServiceCreate.auth_scheme: str`, services.py:126) and never validate the oauth2 credential structure. Credentials are stored via a separate credentials endpoint, but this module's validator is not referenced there either.

Consequence: Requirements 19.2/19.4/19.5/19.6 (token_url HTTPS, SSRF check, ≥1 credential field, default `token_response_path`) are **not enforced** at the API. An operator can register an `oauth2_password_grant` service/credential whose `token_url` is `http://` or a private IP, or with empty `credential_fields`, and the Admin API will accept it. The SSRF check the design says happens "at registration time" (design §Security Invariant 4, which the proxy *relies on*) does not run. The proxy then trusts an unvalidated `token_url`.
Impact: the entire registration-time validation story for auth_scheme=8 is non-functional; the proxy's "trust the stored URL because it was validated at write time" assumption is false. This is both an implementation gap and a security hole.
Fix: import and apply `OAuth2PasswordGrantPayload` (or `validate_token_url_ssrf`) wherever an `oauth2_password_grant` credential payload is accepted; add tests asserting non-HTTPS / private-IP / empty-fields are rejected.

#### [SEV: MEDIUM] [confidence: CONFIRMED] from-template instantiation never pre-populates the oauth2 credential structure (Req 23.5)
`apps/admin-api/src/admin_api/api/services.py:464-621`.

`create_service_from_template` copies `name/display_name/description/base_url/auth_scheme/openapi_url/template_id` into the `services` row. It does **not** read `template.credential_hint` (which for `azure-dashboard-api` carries `token_url`, `credential_fields`, `token_response_path`) and does nothing with it. Requirement 23.5 says instantiating the Azure Dashboard template SHALL pre-populate the credential structure so the operator "only needs to supply the actual username and password values." Nothing in the endpoint touches credentials at all.
Impact: operators get a service with `auth_scheme=oauth2_password_grant` but zero credential scaffolding; they must hand-construct the full payload, defeating the template's purpose. (Likely also flagged by contract reviewer; included because the code path concretely omits the `credential_hint` read.)
Fix: when `template.auth_type == "oauth2_password_grant"`, surface/seed the `credential_hint` into the create response or a credential pre-fill.

#### [SEV: MEDIUM] [confidence: CONFIRMED] `get_template` detail can emit OAuth2 `credential_hint` placeholders but list/registry round-trip of hint is lossy for simple types
`apps/admin-api/src/admin_api/api/service_templates.py:83-92`; `templates/models.py:33-44`.

`CredentialHint` merges simple-auth fields (`field/help/format`) and oauth2 fields (`token_url/credential_fields/token_response_path`) into one flat model with all-optional fields. `get_template` returns `credential_hint.model_dump(exclude_none=True)`. This is functionally OK, but the YAML for simple templates uses `field: value` (literally the string "value"; e.g. gitlab.yaml:13) — a placeholder that will be surfaced verbatim to the UI as `{"field":"value","help":...}`. The `field: value` line appears to be copied from the design's illustrative snippet and is meaningless data shipped to clients. Low-impact but it pollutes every simple template's detail response with a junk `field: "value"` pair.
Fix: drop the `field: value` line from the 11 simple templates, or give `field` a real meaning.

### SUSPECTED

#### [SEV: LOW] [confidence: SUSPECTED] Template endpoints declare `-> JSONResponse` and bypass `response_model`, so no schema validation / OpenAPI typing
`apps/admin-api/src/admin_api/api/service_templates.py:46-93`.

Both handlers return a raw `JSONResponse` and are annotated `-> JSONResponse`. FastAPI therefore performs no `response_model` serialization/validation and the OpenAPI schema for these routes is untyped (`{}`). The design (§Wire Representation) specifies an exact response shape. Not a runtime bug, but it means a field-name typo in `_template_to_list_item` would never be caught and the generated client types are empty. Consistent with neighboring `services.py` style, so likely intentional house style — flagging as SUSPECTED.

#### [SEV: LOW] [confidence: SUSPECTED] `from-template` SSRF check uses literal-IP-only `_is_forbidden_destination`, not DNS-resolving `_validate_test_url`
`apps/admin-api/src/admin_api/api/services.py:507` calls `_is_forbidden_destination` (services.py:98-115), which only blocks IP *literals* and explicitly allows DNS names (returns False for hostnames). The override `base_url` can therefore be a hostname resolving to a private IP and pass. This matches the existing `create_service` behavior (same helper), so it is not a regression and is owned by the security reviewer — noting that the from-template path inherited the weaker check rather than the DNS-resolving `_validate_test_url`.

---

## TYPESCRIPT / REACT

### CONFIRMED

#### [SEV: HIGH] [confidence: CONFIRMED] `from-template` BFF swallows non-2xx into a success-shaped record; picker can render false success
`apps/admin-ui/src/resources/services.ts:329-372` and `apps/admin-ui/src/components/actions/ServiceTemplatePicker.tsx:244-281`.

In the BFF `from-template` handler, on `!resp.ok` it returns `{ record: baseRecord, notice: { type: "error", message } }`. The React `handleSubmit` checks `data?.notice?.type === "error"` (picker.tsx:259) — good. BUT the success path: when `resp.ok` but the admin-api body has no `id` (e.g. a 200/201 with an unexpected body, or `resp.json()` fell back to `{}` via `.catch(() => ({}))` at services.ts:348), the handler returns `service: {}` with `redirectUrl: undefined`. In the picker, `serviceId` resolves to `""` (picker.tsx:264-267), the `else` branch sets `setSubmitSuccess({ serviceId: "" })` (picker.tsx:274), and the UI shows the green "Service created from template successfully" banner (picker.tsx:294-313) **even though no service id came back**. The "View service" button is hidden but the success state is asserted.
Impact: operator sees a success message for a request whose result is unknown; combined with `resp.json().catch(() => ({}))`, a malformed-but-2xx response is reported as success.
Fix: treat a missing `id` on a 2xx as an error, or only show success when `serviceId` is non-empty.

#### [SEV: MEDIUM] [confidence: CONFIRMED] `loading` flag is only cleared in `.finally`, but error path leaves catalog hidden while `error` AND empty-state can both be suppressed
`apps/admin-ui/src/components/actions/ServiceTemplatePicker.tsx:125-148, 369-376`.

`useEffect` sets `setLoading(false)` in `.finally` (good). On fetch error, `templates` stays `[]` and `error` is set. The render gates: empty-state requires `!loading && !error && templates.length === 0` (picker.tsx:369) and main content requires `!loading && templates.length > 0` (picker.tsx:376). That is internally consistent. The concrete bug is narrower: the catch sets `error` to `err.message`, but `ApiClient.resourceAction` resolves with a 2xx envelope even when the BFF returned `templates: []` due to an upstream error (services.ts:233-251 returns a 200-shaped record with empty templates on `!resp.ok`/throw). So an upstream `/v1/service-templates` failure is **indistinguishable from "no templates"** in the UI — the user sees "No templates available." rather than an error. Error surfacing is lost across the BFF boundary.
Fix: have the BFF propagate a failure flag (e.g. `notice.type==="error"`) instead of masquerading as an empty list.

#### [SEV: MEDIUM] [confidence: CONFIRMED] Selected-card highlight matches on `name` fallback, mis-highlighting templates with duplicate names
`apps/admin-ui/src/components/actions/ServiceTemplatePicker.tsx:449-450`.

`isSelected = selectedTemplate?.template_id === tpl.template_id || selectedTemplate?.name === tpl.name`. Since `name` equals `template_id` for the shipped catalog this is harmless today, but the `|| name === name` clause means any two templates sharing a `name` (or a template whose `template_id` is undefined, falling back to `name`) highlight together. The detail panel `key={tpl.template_id ?? tpl.name}` (picker.tsx:453) has the same fallback. Defensive but fragile.
Fix: match on `template_id` only.

### SUSPECTED

#### [SEV: LOW] [confidence: SUSPECTED] `useTemplateInForm` legacy path passes `template_id` as a `?template=` slug the form's BFF resolves via `template-detail` by `slug`, but admin-api detail is keyed by `template_id`
`apps/admin-ui/src/components/actions/ServiceTemplatePicker.tsx:289-291, 700` → `services.ts:265-325` (`template-detail` fetches `/v1/service-templates/{slug}`).

The "Pre-fill form instead" button navigates with `?template=<template_id>`. The `template-detail` BFF then GETs `/v1/service-templates/<slug>` and normalizes `raw.slug`, `raw.auth_scheme`, `raw.openapi_url` (services.ts:288-297). But the admin-api detail response (`service_templates.py:_template_to_list_item`) emits `auth_type` and `openapi_spec_url`, NOT `auth_scheme`/`openapi_url`, and has no `slug` field. So `template-detail` will set `auth_scheme: ""`, `openapi_url: ""`, `slug: ""` for every template — the pre-fill-form path loses auth type and OpenAPI URL. SUSPECTED because it depends on the `ServiceCreateForm` consumer, but the field-name mismatch (`auth_type` vs `auth_scheme`, `openapi_spec_url` vs `openapi_url`) is concrete and present in the diff.
Fix: map `auth_type`→`auth_scheme` and `openapi_spec_url`→`openapi_url` in the `template-detail` normalizer (and derive `slug` from `template_id`).

---

## Summary of highest-value items
1. CRITICAL (Go): scope interceptor + empty token/identity = every `GetCredential` denied in prod; untested because the gRPC test server omits the interceptor. `grpc.go:62-104`, `main.go:79`, `client.go:94`.
2. HIGH (Python): `OAuth2PasswordGrantPayload` SSRF/HTTPS/non-empty validation is dead code — never wired into registration. `credential_service.py:103-156`.
3. HIGH (Go): the redaction-bearing `Emitter.EmitTokenExchanged` is dead; live audit path hand-rolls the event and drops `agent_id` from payload. `emitter.go:147-212`, `main.go:457-471`.
4. HIGH (TS): false-success banner when from-template returns 2xx with no `id`. `ServiceTemplatePicker.tsx:259-275`, `services.ts:348`.
5. MEDIUM (Go): numeric-token `%v` coercion corrupts large tokens; JSONPath object-only. `exchanger.go:194-196`.
