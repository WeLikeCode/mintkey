# Review 03 — Contract & Spec-Compliance Audit

**Feature:** Service Templates + OAuth2 Password Grant
**Branch:** `feature/service-templates` @ `828bd7c`
**Scope:** Read-only verification of implementation vs. `.kiro/specs/service-templates/{requirements,design,tasks}.md` and the canonical proto/OpenAPI/migration contracts.
**Rule applied:** Where implementation diverges from a canonical contract, the bug is in the IMPLEMENTATION — never the contract.

---

## Severity counts

| Severity | Count |
|---|---|
| HIGH | 1 |
| MEDIUM | 2 |
| LOW | 3 |
| INFO | 2 |

The catalog content, error semantics, audit struct, migration, and Pydantic validation are **substantially correct and spec-faithful**. The one material correctness finding is generated-proto drift; the rest are partial-implementation / dead-code / test-coverage gaps.

---

## Findings

### F1 — [HIGH] [high] Generated `vault.pb.go` rawDesc descriptor was NOT regenerated (hand-edit drift)

- **Spec ref:** Design §"Proto Enum Extension"; Task 1.1; Req 19.1.
- **File:** `packages/go/vault/v1/vault.pb.go` (constants at L59, name map L73, value map L84; `file_vault_proto_rawDesc` at L1072).
- **Deviation:** The proto source (`docs/architecture/contracts/vault-adapter/vault.proto:93`) correctly adds `AUTH_SCHEME_OAUTH2_PASSWORD_GRANT = 8`. But the generated Go file only received a 3-line hand edit (the `AuthScheme_AUTH_SCHEME_OAUTH2_PASSWORD_GRANT` constant plus the two convenience maps). A genuine `protoc-gen-go` regeneration ALSO re-serializes the `FileDescriptorProto` into the `file_vault_proto_rawDesc` byte string. Verified: that descriptor blob contains the 8 original enum value names (`UNSPECIFIED`…`MTLS`) but **NOT** `AUTH_SCHEME_OAUTH2_PASSWORD_GRANT`. The embedded protobuf reflection descriptor is therefore inconsistent with the Go constant/maps.
- **Impact:** Any protoreflect-driven path — `protojson` (un)marshalling of the enum by name, gRPC server reflection, descriptor-based validation, `EnumDescriptor().Values()` — will not know value 8 exists. The plain int32 wire path and the convenience maps still work (which is why example tests pass), masking the drift. This is exactly the "skipped regeneration" the task warns against.
- **Suggested fix:** Re-run the proto codegen toolchain (e.g. `buf generate` / `protoc`) against the updated `.proto` so `rawDesc` is regenerated; do not hand-edit the maps. Verify post-fix that the rawDesc contains the new value name (`grep` the descriptor region).

### F2 — [MEDIUM] [medium] Req 23.5 credential pre-population not implemented on instantiation

- **Spec ref:** Req 23.5; Design §"Template Catalog Extension" (azure-dashboard-api).
- **Files:** `apps/admin-api/src/admin_api/api/services.py:464-621` (`create_service_from_template`); `apps/admin-ui/src/components/actions/ServiceTemplatePicker.tsx:44`.
- **Deviation:** Req 23.5 says instantiating the `azure-dashboard-api` template SHALL "pre-populate the credential structure with the correct token_url, field names, and token_response_path so the operator only needs to supply the actual username and password values." The from-template endpoint inserts only the `services` row — it never stages/returns the credential structure, and the response omits `credential_hint`. The UI declares `credential_hint?` in its template type (line 44) but never renders it or uses it to pre-fill a credential form (only `config_notes` + `version` are shown in the detail panel, L576-592). The credential-hint *data* exists in the catalog (Req 23.3 satisfied) and the detail GET returns it, but the instantiation flow does not act on it.
- **Impact:** Operator who instantiates Azure Dashboard API gets a service with no credential scaffolding; they must hand-construct the full `{token_url, credential_fields, token_response_path}` JSON. The "only supply username/password" UX promised by 23.5 is not delivered.
- **Suggested fix:** Either (a) have the from-template response echo the template's `credential_hint` so the UI can pre-fill the credential form, and have the UI render it; or (b) stage a credential skeleton. At minimum surface `credential_hint` in the 201 response and consume it in the picker.

### F3 — [MEDIUM] [high] `TokenExchangedEvent` struct + `EmitTokenExchanged()` are dead code; real emission uses a divergent path

- **Spec ref:** Task 9.3; Design §6 "Audit Event: token.exchanged"; Req 22.1.
- **Files:** `apps/proxy-plugin/internal/audit/emitter.go:50-57` (struct), `:158-212` (`EmitTokenExchanged`); actual emission at `apps/proxy-plugin/cmd/proxy-plugin/main.go:449-462`.
- **Deviation:** Task 9.3 says "Define `TokenExchangedEvent` struct … Emit after every exchange attempt." The struct IS defined exactly per design (6 fields, no credential/token leakage). However it is **never used in production** — verified no references to `TokenExchangedEvent`/`EmitTokenExchanged` outside `emitter.go` and its `_test.go`. The live path instead enqueues a raw `auditq.Event` with payload `{token_url_host, success, latency_ms}` and envelope `tenant_id` / `actor_id`(=agent_id) / `target_id`(=service_id). All 6 required fields ARE present (split across envelope + payload), so **Req 22.1 is functionally satisfied**, but via a different mechanism than the spec/task describes, and the spec'd, well-tested emitter method is dead code.
- **Impact:** Functional behavior is compliant; the risk is maintenance/divergence — the tested `EmitTokenExchanged` (with its 1s timeout, host-only redaction, OTel span) is bypassed, so its test coverage does not exercise the real emission path. If the two drift, tests stay green while production changes.
- **Suggested fix:** Route the live emission through `Emitter.EmitTokenExchanged(TokenExchangedEvent{...})` (or delete the dead struct/method and document the auditq path as canonical). Confirm the auditq consumer maps `actor_id`→agent_id / `target_id`→service_id into the persisted `token.exchanged` record.

### F4 — [LOW] [high] All 12 property-based test tasks are absent as PBT (no `rapid` / `hypothesis`)

- **Spec ref:** Design §"Testing Strategy (Reqs 19–23)" mandates `pgregory.net/rapid` (Go) and `hypothesis` (Python) with a specific tag format; optional tasks 3.2, 3.3, 6.2, 6.3, 6.4, 7.2, 7.3, 7.4, 9.4, 9.5, 9.6, 10.2.
- **Evidence:** `grep` confirms **zero** uses of `pgregory.net/rapid`/`rapid.Check` in `apps/proxy-plugin`+`apps/vault-adapter`, and **zero** `hypothesis`/`@given` in `apps/admin-api`. The underlying logic IS covered by example-based unit tests (see coverage table), but none are property tests and none carry the `Feature: service-templates, Property N` tags.
- **Impact:** These are all optional `[ ]*` tasks left correctly unchecked — **not** false-done. But Properties 1–12 are not machine-verified across an input space as the design intends; edge cases (random JSONPath shapes, arbitrary status codes, fuzzy expiry) are only spot-checked.
- **Suggested fix:** If PBT coverage is a release gate, implement the 12 rapid/hypothesis tests with the tagged format. Otherwise document the accepted gap in the remediation matrix.

### F5 — [LOW] [medium] No automated test exercises `from-template`, OAuth2 payload validation, or 404/409/422 error codes (Python)

- **Spec ref:** Tasks 3.4, 5.4 (both optional `[ ]*`); Design Error Handling table; Reqs 3.2, 4.5, 19.x.
- **Evidence:** `apps/admin-api/.../test_service_templates.py` only tests list/detail (count=13, shape, https, category/search filters, version). `grep` finds **no** test referencing `from-template`, `OAuth2PasswordGrantPayload`, `template_not_found`, or `service_name_taken`. The 404/409/422 paths and the HTTPS/SSRF/non-empty validators have no regression coverage.
- **Impact:** Optional tasks, so not false-done — but the error-semantics contract (the central concern of this audit) is unguarded against regression. The code itself reads correct (see F-INFO below).
- **Suggested fix:** Add integration tests for from-template happy path + 404/409/422 and unit tests for `OAuth2PasswordGrantPayload` (non-HTTPS reject, empty credential_fields reject, default `$.access_token`, arbitrary field names).

### F6 — [LOW] [medium] `from-template` 409 duplicate check is a non-atomic SELECT (TOCTOU)

- **Spec ref:** Req 4.5 (409 `service_name_taken`).
- **File:** `apps/admin-api/src/admin_api/api/services.py:519-534`.
- **Deviation:** The duplicate check is a `SELECT … WHERE slug = :slug` followed by an INSERT. Two concurrent from-template calls with the same name can both pass the SELECT, then one INSERT hits the DB-level `uq_services_tenant_slug` constraint (migration `004-services.yaml:89-100`) and surfaces a raw 500 instead of a clean 409. The status code IS 409 in the common case (matches spec), so this is a robustness edge, not a primary deviation.
- **Suggested fix:** Catch the unique-constraint `IntegrityError` and map it to the same 409 `service_name_taken` body, or rely on the constraint alone and translate the error.

### F7 — [INFO] Proto value, Go constant, and YAML catalog content are fully spec-compliant

- `vault.proto:93` → `AUTH_SCHEME_OAUTH2_PASSWORD_GRANT = 8` (exact value). Go injector constant `AuthSchemeOAuth2PasswordGrant = 8` (`injector.go:26`) and pb.go convenience maps agree (the only defect is the rawDesc, F1).
- Catalog has exactly **13** templates (12 + Azure Dashboard). Every template carries all 12 required fields. Programmatic cross-check confirms **every** `name`, `auth_type`, `category`, `base_url`, and `openapi_spec_url` matches Reqs 5–16 and 23 **exactly** — no typos, no wrong categories, all `base_url`/`token_url` are HTTPS, all `version` = `"1.0.0"` (valid semver).
- Error semantics verified correct: detail 404 → `mintkey:code=template_not_found` (`service_templates.py:76-82`); from-template 404 template_not_found, 409 `service_name_taken`, 422 `forbidden_destination` (`services.py:480-534`); records `template_id` metadata (L569), emits `service.registered` audit with `template_id` in payload (L576-590), change-channel notify (L593-602), RLS via `set_tenant_context` (L517).
- Audit struct `TokenExchangedEvent` (`emitter.go:50-57`) has exactly the 6 spec'd fields, host-only via `ExtractHost`→`u.Hostname()`, no credential/token fields (matches Req 22.1 / Property 11 — modulo the dead-code routing in F3).
- Pydantic models match Reqs 18/19: `ServiceTemplate.validate_semver` (`models.py:63-71`); `OAuth2PasswordGrantPayload` HTTPS + SSRF + non-empty + default `$.access_token` (`credential_service.py:103-155`).

### F8 — [INFO] DB migration 017 is correct and consistent

- `017-services-template-id.yaml`: `addColumn template_id VARCHAR(128) nullable:true`, rollback `dropColumn` present, id `"017-services-template-id"` / author `mintkey` match the conventions of 001–016. **Included** in `db.changelog-master.yaml:50-52`. No separate RLS needed — `services` already has `tenant_isolation` RLS (migration `004-services.yaml:102-118`) which the new column inherits. Tenant-scoping consistent.

---

## Task verification: `[x]` claimed-done tasks

| Task | Status | Notes |
|---|---|---|
| 1.1 Proto enum + Go types | **DEVIATION** | Proto + constant + injector const correct; generated `pb.go` rawDesc NOT regenerated (F1). `types.go` `OAuth2PasswordGrantCredential` correct. |
| 2.1 service_templates.yaml (12+1) | VERIFIED | 13 templates, all fields, all values match spec exactly (F7). |
| 2.2 ServiceTemplate / CredentialHint models | VERIFIED | `models.py` matches design; semver validator present. |
| 2.3 TemplateRegistry load/list/get/filter | VERIFIED | `registry.py` import-time load, case-insensitive search, malformed-skip with warning, no startup fail. |
| 3.1 OAuth2PasswordGrantPayload validation | VERIFIED | HTTPS + SSRF + non-empty + default path; integrates S-SEC-1 list. |
| 4 Checkpoint (Python tests pass) | VERIFIED (weak) | List/detail tests exist; from-template & payload untested (F5). |
| 5.1 GET list endpoint | VERIFIED | category+search params, all fields incl. version. |
| 5.2 GET detail endpoint | VERIFIED | 404 `template_not_found`; returns config_notes + credential_hint. |
| 5.3 POST from-template | **DEVIATION** | Core flow correct (404/409/422, audit, notify, RLS, template_id metadata). Req 23.5 credential pre-population not done (F2); 409 TOCTOU (F6). |
| 6.1 TokenExchanger | VERIFIED | POST JSON body, headers, 10s timeout, JSONPath extract, typed errors. |
| 7.1 TokenCache (Get/Put/DetermineExpiry) | VERIFIED | RWMutex, 30s buffer, JWT-exp→expires_in→300s priority, memory-only. |
| 8 Checkpoint (Go tests pass) | VERIFIED | Unit tests present & green-shaped. |
| 9.1 Injector enhancement | VERIFIED | `case AuthSchemeOAuth2PasswordGrant` sets Bearer; strips agent auth. |
| 9.2 Egress orchestration | VERIFIED | `oauth2_handler.go` + `main.go` wire cache→exchange→degrade→inject→502; graceful degradation correct. |
| 9.3 token.exchanged emission | **DEVIATION** | Struct defined per spec but dead; real emission via auditq path (F3). Fields functionally complete; spec'd emitter bypassed. |
| 10.1 Vault round-trip + scope | VERIFIED | scopeInterceptor enforces `vault.read` on GetCredential (Req 22.5); auth_scheme stored as opaque int, scheme-agnostic round-trip. |
| 11 Checkpoint | VERIFIED | grpc_test.go covers round-trip + scope. |
| 12.1 Admin UI picker | VERIFIED | Category grouping/collapse, search, detail panel (config_notes+version), from-template submit (services.ts BFF). |
| 13 Final checkpoint | VERIFIED (weak) | Same caveat as F4/F5 — no PBT, thin Python error-path coverage. |

**False-done:** none. No `[x]` task is wholly unimplemented. The three DEVIATIONS (1.1, 5.3, 9.3) are partial: the claimed artifact exists but has a correctness/completeness gap.

## Optional task coverage: `[ ]*`

| Task | Coverage | Notes |
|---|---|---|
| 2.4 Registry/model unit tests | PARTIAL | List/detail integration tests cover count/filter/search/shape; no direct malformed-skip or model-validation unit test. |
| 3.2 PBT credential validation (P1, hypothesis) | ABSENT | No hypothesis anywhere. |
| 3.3 PBT token_url HTTPS/SSRF (P3) | ABSENT | No hypothesis. |
| 3.4 Unit tests OAuth2PasswordGrantPayload | ABSENT | No test references the model (F5). |
| 5.4 Integration tests template API | PARTIAL | List/detail covered; from-template + 404/409 NOT covered (F5). |
| 6.2 PBT exchange request construction (P4) | ABSENT | No rapid. |
| 6.3 PBT JSONPath extraction (P5) | ABSENT | No rapid. |
| 6.4 PBT non-2xx→502 (P6) | ABSENT | No rapid. |
| 6.5 Unit tests TokenExchanger | PARTIAL | `injector_test.go`/handler tests touch exchange indirectly; no dedicated timeout/DNS-failure unit test found in exchanger pkg. |
| 7.2 PBT cache keyed retrieval (P7) | ABSENT | Covered example-style by `TestTokenCache_Get_MissForDifferentKey`, but not PBT. |
| 7.3 PBT expiry priority (P8) | ABSENT | Covered example-style by `TestDetermineExpiry_*`, not PBT. |
| 7.4 PBT cache threshold (P9) | ABSENT | Covered example-style by `TestTokenCache_Get_*Boundary/NearExpiry`, not PBT. |
| 7.5 Unit tests TokenCache | COVERED | `TestTokenCache_EmptyOnConstruction`, thread-safety, overwrite — solid. |
| 9.4 PBT graceful degradation (P10) | ABSENT | Covered example-style by `TestHandleOAuth2PasswordGrant_ExchangeFails_*`, not PBT. |
| 9.5 PBT audit completeness/host redaction (P11) | ABSENT | Covered example-style by `TestEmitTokenExchanged*` + `TestExtractHost`, not PBT. |
| 9.6 PBT sensitive-data exclusion (P12) | ABSENT | Covered example-style by `TestTokenExchangedEventNoCredentialFields`, not PBT. |
| 9.7 Integration full OAuth2 flow (testcontainers) | PARTIAL | `oauth2_handler_test.go` covers orchestration with mocks; no testcontainers vault+token-endpoint integration. |
| 10.2 PBT credential round-trip (P2) | ABSENT | Covered example-style by `TestGRPCOAuth2PasswordGrant_RoundTrip/_MinimalPayload`, not PBT. |
| 12.2 vitest UI tests | ABSENT | No vitest test file for the picker in the diff. |

**Pattern:** Every one of the 12 PBT tasks is ABSENT *as PBT*; 10 of the 12 underlying Properties have decent example-based coverage; the two with the weakest non-PBT backstop are Property 1 (3.2) and Property 3 (3.3) — Python validation has **no** automated test at all (F5).
