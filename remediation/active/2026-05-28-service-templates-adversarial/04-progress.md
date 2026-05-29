# Orchestration State — Service-Templates Remediation

**Session:** `2026-05-28-service-templates-adversarial`
**Branch:** `feature/service-templates` (base `main`, started @ `828bd7c`)
**Repo:** `/Users/alexandruiacobescu/gooseProjects/mintkey`
**Owner decisions (locked 2026-05-28):** SCOPE-A = fix authz/cross-tenant in this branch; SCOPE-B = fix ALL severities; SCOPE-C = implement ALL 19 optional tasks; SCOPE-D = install protoc-gen-go + regenerate for BUG-8.
**Findings source:** `00-findings-and-intake.md` + `reviews/01..05`.

## Definition of Done (DoD)
- [ ] All CRITICAL/HIGH/MEDIUM/LOW defects (BUG-1..19 + TEST-INFRA + SCOPE-A) fixed, each test-first where applicable.
- [ ] `cd apps/proxy-plugin && go test ./... -race` GREEN (baseline: 46 pass).
- [ ] `cd apps/vault-adapter && go test ./... -race` GREEN (baseline: 33 pass).
- [ ] Python service-templates tests GREEN under PINNED venv `apps/admin-api/.venv/bin/python -m pytest` (baseline: 61 pass) — NOT anaconda 3.9.7.
- [ ] All 19 optional Kiro tasks implemented with real assertions + PBT deps (`rapid`, `hypothesis`) wired.
- [ ] `.kiro/specs/service-templates/tasks.md` optional tasks flipped `[ ]*`→`[x]*` as completed.
- [ ] Final fresh-Opus full-DoD review: PASS.

## Baseline (established by review agent 04-tests, 2026-05-28)
Go proxy-plugin 46 PASS / vault-adapter 33 PASS / Python 61 PASS (correct venv). `go test -race` clean on cache. Existing tests shallow: 0/19 optional COVERED, miss BUG-1 & SSRF.

## Chunk plan
### Wave F — fixes (severity order; serialize where files overlap)
| Chunk | Bugs | Files | Notes |
|---|---|---|---|
| FIX-1 | BUG-1 | proxy `cmd/.../main.go`, `internal/vault/client.go`, vault-adapter `grpc.go` | reproduce-first (interceptor-on integration). BLOCKS runtime. |
| FIX-AUTH | SCOPE-A | `api/services.py`, auth/CSRF dep, session→tenant binding | flag sibling write endpoints |
| FIX-2 | BUG-2/9 | `services/credential_service.py` + credential write path | wire SSRF validation |
| FIX-3 | BUG-3/6/12/17 | `internal/credential/exchanger.go` | dial IP-allowlist + no-redirect + resp-header timeout + JSONPath safety + safe err body |
| FIX-4 | BUG-4/14 | `internal/cache/token_cache.go` | expiry clamp/overflow/past-exp + size cap |
| FIX-5 | BUG-5 | `internal/egress/oauth2_handler.go` | singleflight per (tenant,service) |
| FIX-6 | BUG-10 | `cmd/.../main.go`, `internal/audit/emitter.go` | route via emitter + agent_id (serialize after FIX-1) |
| FIX-7 | BUG-8 | `packages/go/vault/v1/vault.pb.go` | protoc-gen-go regen |
| FIX-8 | BUG-7/16/19 | `ServiceTemplatePicker.tsx`, `resources/services.ts` | banner/error/field-mismatch |
| FIX-9 | BUG-11 | `api/services.py`, UI | credential pre-pop (after FIX-8/FIX-AUTH) |
| FIX-10 | BUG-13/15/18 | `service_templates.yaml`, services validation | base_url DNS SSRF, YAML junk, TOCTOU |

### Wave T — optional tasks (19)
| Chunk | Tasks | Notes |
|---|---|---|
| T-deps | — | add `pgregory.net/rapid` (2 go.mod) + `hypothesis` (pyproject) |
| T-cache | 7.2,7.3,7.4,7.5 | PBT + unit on hardened cache |
| T-exchanger | 6.2,6.3,6.4,6.5 | PBT + unit on hardened exchanger |
| T-egress | 9.4,9.5,9.6,9.7 | PBT + testcontainers integration |
| T-vault | 10.2 | round-trip PBT |
| T-py | 2.4,3.2,3.3,3.4,5.4 | registry + payload + from-template integration |
| T-ui | 12.2 | real vitest render tests (replace string-grep) |

## Round history (append-only)
- R0 (2026-05-28): 5-agent adversarial review complete; findings consolidated; intake gate passed; owner decisions locked. Baseline captured. → starting FIX-1.
- R1 (2026-05-28): FIX-1 attempt 1 (commit `58117a5`) → REVIEWER **FAIL** (strike 1/3). Two defects: (a) MAKE-OR-BREAK — fix relies on undocumented env vars `MINTKEY_VAULT_PROXY_TOKEN`/`_IDENTITY_ID` absent from all compose files; vault-adapter skips identity registration when token empty ⇒ stock `docker compose up` still 502s. (b) Regression guard illusory — success test hand-builds metadata, bypasses production `vault.NewClient().GetCredential()`; reverting client fix leaves tests GREEN. Interceptor untouched ✓, suites green ✓, hygiene ✓. → re-dispatch FIX-1 attempt 2 with provisioning + cross-module-test requirements.
- R2 (2026-05-28): FIX-1 attempt 2 (commit `c58baab`) → REVIEWER **PASS**. Compose provisions matching `svcid_proxy`/token on BOTH services by default; new `apps/vault-adapter/vaulttest/` + `apps/proxy-plugin/internal/vault/xmodule_integration_test.go` drives production `vault.NewClient` against real `scopeInterceptor`; reviewer flipped GREEN→FAIL by blanking the client token send (guard is real). Suites green, vet clean, interceptor untouched. **FIX-1 DONE.** 3 non-blocking carry-overs (below).

## Carry-over cleanups (fold into FIX-10)
- CO-1: `apps/proxy-plugin/internal/vault/xmodule_integration_test.go:37-39` has a FALSE comment — `devProxyToken="mk_vault_proxy_dev_secret_32b!!!!"` ≠ compose value `"mk_vault_proxy_dev_shared_secret!"`. Test is self-consistent but doesn't pin the compose value. Fix comment AND pin the compose literal so a compose typo is caught.
- CO-2: `apps/proxy-plugin/internal/vault/client.go:76` `NewClient(addr, token string, serviceIdentityID ...string)` — make identity param EXPLICIT (variadic silently defaults to "").
- CO-3: delete stale `apps/vault-adapter/internal/server/proxy_client_bug_test.go` (from `58117a5`) — superseded by xmodule test; its doc falsely claims to drive the production client (FAIL-2 anti-pattern).

- R3 (2026-05-28): parallel FIX-2 ∥ FIX-3.
  - FIX-3 (commit `78088ba`) → REVIEWER **PASS**. Prod deny-default (`main.go:199` NewTokenExchanger), allowPrivate bypass test-only/not env-driven; dial-time resolved-IP guard + CheckRedirect DNS-rebind-safe + flip-verified; numeric-token rejected; 3s ResponseHeaderTimeout; no error-body leak; `-race` green. **FIX-3 DONE.** Carry-over CO-4 → T-exchanger.
  - FIX-2 (commit `fb86aba`) → REVIEWER **FAIL** (strike 1/3). Create-path wiring CORRECT (5 tests, flip-verified, 61 baseline green, real shared SSRF helper that resolves DNS). BUT sibling write path `rotate_credential` (`apps/admin-api/src/admin_api/api/credentials.py:429`, `put_credential`) persists oauth2 `value` with NO validation ⇒ register-benign-then-rotate-malicious re-opens BUG-2/9. Also unused direct import `validate_token_url_ssrf` at `:39`. → re-dispatch FIX-2 attempt 2: extend validation to rotate_credential + regression test, keep create-path fix.

## Carry-over cleanups
(FIX-10 carries CO-1/2/3 from FIX-1.)
- CO-4 → fold into **T-exchanger**: add an injected-resolver/dialer test proving the DEFAULT (deny) exchanger ALLOWS a routable public IP (current `TestExchange_PublicEndpointAllowed` uses the allowPrivate bypass, proves nothing about default). Fix `TestSSRF_LinkLocalRefused`/`TestSSRF_PrivateRangeRefused` — they pass for the WRONG reason (10s whole-request timeout to non-routable IP; would pass with NO guard). Correct the confused comments at exchanger_test.go:106-119.

- R4 (2026-05-28): FIX-2 attempt 2 (commit `f60f90b`) → REVIEWER **PASS**. Both create_credential + rotate_credential validate oauth2 token_url (HTTPS+SSRF+non-empty fields); reviewer enumerated all write paths (only those two persist via put_credential), flip-verified, unused import gone (ruff clean), 21 unit + 61 integration green on pinned 3.12.12. **FIX-2 DONE.** All 3 CRITICALs (BUG-1/2/3) now closed.

- R5 (2026-05-28): parallel FIX-4 ∥ FIX-AUTH — both **PASS**.
  - FIX-4 (`274f2e8`): clamp-before-multiply (flip-proven), past-exp fall-through (Get miss), far-future→24h clamp, MaxCacheSize=10k evict-expired-then-earliest under Lock, mutex preserved, `-race`+`-count=2` green. **DONE.** Carry CO-5 → T-cache: `TestTokenCache_SizeCap_ThreadSafe` re-implements eviction inline (localCap=100) instead of calling real Put/evictLocked — make it drive the SUT.
  - FIX-AUTH (`b57e3cb`): `require_tenant_session` on create/from-template/update/delete; real scoping (sessions.tenant_id + operators.is_platform_admin); cross-tenant 403 flip-verified; the 7 test_services.py failures PROVEN pre-existing (identical at parent `274f2e8`, cause = mintkey:ssrf_rejected/dns on /test endpoints, NOT the guard). **DONE.** Residual: `/test` + `/{id}/test`+`/test-transient` still unguarded (read/write creds) → new chunk FIX-AUTH2.

## Carry-over cleanups
(FIX-10 carries CO-1/2/3 from FIX-1. T-exchanger carries CO-4. T-cache carries CO-5.)
- FIX-AUTH2 (new chunk): apply `require_tenant_session` to `POST /v1/tenants/{tid}/services/{id}/test` and `POST /v1/tenants/{tid}/services/test-transient` (services.py:~722,~869). Their existing tests are red on a pre-existing DNS/SSRF env issue; the authz test must assert 403 cross-tenant which fires BEFORE the SSRF check.

- R6 (2026-05-28): parallel FIX-5 ∥ FIX-8.
  - FIX-8 (`7218414`) → REVIEWER **PASS-WITH-DEFERRAL**. All 4 BFF/handler fixes (BUG-7a/7b/16/19) correct + 9 REAL handler-invocation vitest tests, flip-verified (9 fail pre-fix); no new tsc errors (161==161); lone full-suite failure is unrelated `test_permissions`. Browser ESCALATE legitimate (no jsdom/@testing-library/browser-mode in project). **DONE.** Deferred: BUG-7a banner *display* + BUG-19 *visual* highlight are source-inspection-only → T-ui must add a render harness (jsdom+@testing-library/react) and re-verify them as part of task 12.2.
  - FIX-5 (`3ce81f4`) → REVIEWER **FAIL** (strike 1/3). Singleflight impl + tests are rigorous (50-goroutine barrier, count==1, flip-verified, race-clean), BUT make-or-break: the ONLY prod construction site `cmd/proxy-plugin/main.go:447` sets Cache+Exchanger only — `SF` nil → `oauth2_handler.go:148` falls through to non-coalesced `doExchange()` for ALL real traffic. BUG-5 unfixed in prod. → re-dispatch attempt 2: wire a shared `*singleflight.Group` at main.go:447 + a guard test that the production-construction path coalesces. (Minor: x/sync tagged `// indirect` though now direct.)

## Strike counter
| Chunk | Strikes | Max | Status |
|---|---|---|---|
| FIX-1 | 1 | 3 | PASS @ c58baab |
| FIX-2 | 1 | 3 | PASS @ f60f90b |
| FIX-3 | 0 | 3 | PASS @ 78088ba |
| FIX-4 | 0 | 3 | PASS @ 274f2e8 |
| FIX-AUTH | 0 | 3 | PASS @ b57e3cb |
| FIX-8 | 0 | 3 | PASS(deferral) @ 7218414 |
| FIX-AUTH2 | 0 | 3 | PASS @ 24b649d |
| FIX-5 | 2 | 3 | PASS @ 21763db |
| FIX-9 | 0 | 3 | PASS @ 165809e |
| FIX-6 | 0 | 3 | PASS @ 1077925 |
| FIX-7 | 0 | 3 | PASS @ dcd1a82 |
| FIX-10 | 1 | 3 | PASS @ ad85753 |

### ✅ WAVE F COMPLETE — all 12 fix chunks PASS (FIX-1,2,3,4,5,6,7,8,9,10,AUTH,AUTH2).

- R10 (2026-05-29): parallel FIX-7 ∥ FIX-10(a2) — both **PASS**.
  - FIX-7 (`dcd1a82`): clean generator-shaped regen of vault.pb.go (protoc-gen-go); descriptor now has enum value 8 by name+number (independently verified, fails on parent `63b0a57`); byte-math exact; both Go modules `-race` green; vault.proto untouched. **DONE.** (Non-blocking: file has no protoc-gen-go version header so toolchain version unverifiable from artifact — diff is regen-consistent.)
  - FIX-10 attempt 2 (`ad85753`): extracted ONE shared `resolve_hostname_is_private` helper (services.py delegates; validate_token_url_ssrf unchanged → FIX-2's 21 credentials tests still green); BUG-13 tests narrowed + flip-verified (DB resolution not poisoned); BUG-18 now behavioral (no inspect.getsource); 9/9 + 64 templates + 7 pre-existing unchanged. **DONE.**

- R11 (2026-05-29): T-deps (`5457eec`) → orchestrator-verified **PASS** (trivial additive dep-add). rapid v1.3.0 in both go.mod (`// indirect` until PBT chunks import it), hypothesis 6.155.0 in admin-api; uv.lock diff additive-only (hypothesis+sortedcontainers, zero other version changes); Go smoke 100-check rapid tests green both modules. **DONE.**

- R12 (2026-05-29): parallel FIX-10b ∥ T-py — both **PASS**.
  - FIX-10b (`a731325`): CO-1 compose secret pinned + comment fixed; CO-2 `NewClient` identity explicit (non-variadic), all call sites updated; CO-3 stale `proxy_client_bug_test.go` deleted; both modules `-race` green. **DONE.** (Cosmetic: file-header doc comment still shows 2-arg shorthand — non-blocking.)
  - T-py (`24d1ac0`): tasks 2.4/3.2/3.3/3.4/5.4 + CO-6. Reviewer FLIP-proved Property 3 PBT catches a weakened validator (genuine, non-vacuous); narrow socket patch (DB unpoisoned); real DB-backed integration (5.4); CO-6 now real A→B 403; 56 tests pass on 3.12.12; baseline 7-failure set unchanged; no production code touched. **Kiro tasks.md: 2.4,3.2,3.3,3.4,5.4 → [x]*.** **DONE.**

## ✅ ALL 19 optional-task Kiro marks complete (0 remaining `[ ]*`, 19 `[x]*`). 29 commits since main.

- R15 (2026-05-29): parallel T-egress ∥ CO-7 — both **PASS**.
  - T-egress (`8811034`): rapid PBT Properties 10/11/12 + no-mock full-flow integration 9.7. 9.6 is a REAL secret/token VALUE-absence check (flip-proven: leaking the token fails); 9.4 502-only-after-expiry boundary flip-proven; 9.5 host-only + complete. **Kiro 9.4-9.7 → [x]* (`94f212c`).** **DONE.**
  - CO-7 (`e8251ee`): react/react-dom deduplicated to single 18.3.1 matching production AdminJS (no React 19 in tree); 13 render tests green under React 18; no new failures/tsc errors; deps-only. **DONE.**

## ✅ Phase F COMPLETE — final full-DoD Opus review: **READY TO MERGE**.
- R16 (2026-05-29): Final reviewer independently re-ran ALL suites: proxy-plugin 13 pkgs green, vault-adapter 7 pkgs green, admin-api 151 pass (+7 pre-existing SSRF/DNS), admin-ui 409 pass (+1 pre-existing test_permissions), tsc 84<161 (0 new). High-risk fixes BUG-1/2/3/8/10 + SCOPE-A spot-verified live. 19/19 optional tasks `[x]*`, 4 spot-checked genuine + flip-discriminating. Coherence: FIX-3/4/5/9 guards intact, no silent undo. 29 commits, NO Co-Authored-By, conventional. Known-reds = documented pre-existing/environmental only. **VERDICT: READY TO MERGE.** No re-orchestration needed.

## POST-SESSION (deploy prep)
- R17 (2026-05-29): **BUG-20 found during pre-deploy investigation** (the "READY TO MERGE" missed it). The vault-adapter scopeInterceptor rejects ALL unauthenticated callers; FIX-1 wired only the proxy. **admin-api** called vault-adapter via plain insecure_channel with no identity → new vault-adapter would PermissionDenied admin-api's Put/GetCredential → break credential ops. Fixed (`595a2da`, FIX-VAULT-AUTH): admin-api sends `svcid_admin_api` identity+token (metadata on Put/Get/ListVersions); vault-adapter registers `svcid_admin_api` [vault.read,vault.put] at startup; compose provisions matching token both sides. REVIEWER PASS: caller audit complete (only proxy+admin-api external), value-coherence traced (sent==registered), Go scope test flip-verified, Python metadata test real, proxy intact, suites green. Lesson: scope-interceptor callers must be audited repo-wide, not just the proxy.
- Local deploy so far: admin-api+admin-ui rebuilt from branch & restarted (`--no-deps`, postgres id 823b3bd5 unchanged, data 2/3 preserved, 13 templates live). Next: rebuild+deploy admin-api(re: BUG-20)+vault-adapter+proxy-plugin for full branch.

## SESSION COMPLETE. Branch `feature/service-templates` @ 31 commits, local (NOT pushed — awaiting user authorization). Non-blocking housekeeping follow-up: /test endpoints' 7 DNS/SSRF sandbox failures, `metrics.go:110` vet, `go.work` non-existent remote.

- R14 (2026-05-29): parallel T-exchanger ∥ T-vault — both **PASS**.
  - T-exchanger (`b270c5f`): rapid PBT 6.2/6.3/6.4 (Properties 4/5/6, genuine + flip-verified — neutering isBlockedIP fails refusal tests fast), unit 6.5; CO-4(a) public-allow proven via isBlockedIP+injected net.Pipe (hermetic), CO-4(b) refusal tests now assert guard+<400ms (flip-verified), CO-4(c) comments fixed. **DONE.**
  - T-vault (`665da91`): rapid PBT Property 2 round-trip through REAL scoped Put→Get gRPC path, `reflect.DeepEqual`, omitempty/nil-headers edge, flip-verified (dropping token_request_headers on store fails), deterministic. **DONE.**
  - Orchestrator committed Kiro marks 6.2-6.5 + 10.2 (`02f2ab4`).
## Wave T remaining: T-exchanger(6.2-6.5+CO-4) ∥ T-vault(10.2); then T-egress(9.4-9.7) ∥ CO-7(UI React align); then Phase F final review. [Remaining test chunks: implementer does NOT edit tasks.md — orchestrator flips marks after review, to avoid concurrent-edit races.]

- R13 (2026-05-29): parallel T-cache ∥ T-ui — both **PASS**.
  - T-cache (`c176471`): rapid PBT Properties 7/8/9 (100 cases each, genuine, flip-verified — breaking 30s threshold fails P9), unit 7.5, CO-5 now drives real Put under 300 goroutines race-clean. **Kiro 7.2-7.5 → [x]*.** **DONE.**
  - T-ui (`1da2761`): jsdom + @testing-library/react harness via vitest workspace (node + render projects); 13 real render tests; FIX-8 (error-vs-success banner) + BUG-19 (template_id highlight) + FIX-9 (credential-hint-panel) re-verified in rendered DOM; node-env tests unaffected; full suite 409 pass + 1 pre-existing; tsc 84<161 no new errors. **Kiro 12.2 → [x]*.** **DONE.** **CO-7 (note):** harness added React 19.2.6 devDep while prod AdminJS = React 18.3.1 (^18.2.0) — dev/prod version split; align dev React to 18.x.

## Wave T (optional tasks) — sequencing
T-deps FIRST (PBT prereq). Then: FIX-10b(Go) ∥ T-py; T-cache ∥ T-ui; T-exchanger ∥ T-vault; T-egress. Kiro `tasks.md` `[ ]*`→`[x]*` marked within each test chunk. NOTE: `go mod tidy` can't fully run in sandbox (go.work references non-existent github.com/mintkey remote) — use `go get pgregory.net/rapid` + verify `go build`/`go test`.

- R9 (2026-05-29): parallel FIX-6 ∥ FIX-10.
  - FIX-6 (`1077925`) → REVIEWER **PASS**. token.exchanged routed through live `audit.EmitTokenExchanged`; emitter wired in main():97; agent_id from JWT sub (main.go:289→503); double-flip-verified (drop agent_id→fail, disable emission→fail); host-only + no-secret content-asserted; `-race` clean. **DONE.**
  - FIX-10 (`63b0a57`) → REVIEWER **FAIL** (strike 1/3). Production CODE for BUG-13/15/18 is CORRECT (reviewer verified by direct unit calls: DNS-resolved SSRF works, 13 templates load w/ meaningful fields, atomic IntegrityError 409, FIX-AUTH/AUTH2/FIX-9/FIX-8 all intact). BUT: (1) implementer's "73 pass" claim FALSE — actual `test_fix10_bugs.py` = 3 failed/6 passed; (2) 3 BUG-13 tests broken — `patch("...services.socket.getaddrinfo")` poisons asyncpg DB resolution during require_tenant_session → OSError before SSRF check; (3) `test_bug18_409_comes_from_integrity_error_path` is a source-grep non-test (inspect.getsource + dead _fake_execute); (4) BUG-13 is a THIRD copy of DNS-SSRF logic despite commit claiming reuse. → attempt 2: keep the correct code, reuse/extract ONE shared SSRF helper, fix the 3 test mocks (narrow patch / unit-test the helper), replace the BUG-18 source-grep with a behavioral test, and ACTUALLY run green.

- R8 (2026-05-29): parallel FIX-5(a3) ∥ FIX-9 — both **PASS**.
  - FIX-5 attempt 3 (`21763db`): extracted `h.newOAuth2Deps()` (sole prod deps site, called by `handleOAuth2PasswordGrant`); guard now FLIP-proven — dropping `SF: h.sfGroup` fails both `TestProductionPath_NewOAuth2Deps_SFIsWired` and the 50→1 coalescing test. **DONE.** (Note: `go mod tidy` can't RUN in sandbox due to go.work + non-existent github.com/mintkey remote — pre-existing, go.mod/go.sum untouched. Flag for final review env note.)
  - FIX-9 (`165809e`): from-template returns `credential_hint` (token_url/field-names/token_response_path) per Req 23.5, hints-only, NO persistence, FIX-AUTH 403 + FIX-8 mapping intact (reviewer verified real A→B 403), 64 pytest + 5 vitest green. **DONE.** Carry-overs: CO-6 → T-py (tighten mis-named `test_from_template_cross_tenant_still_403` — it sends NO session, accepts 401, doesn't test tenant scoping; make it authenticated A→B asserting 403); FIX-9 credential-hint-panel render → T-ui (source-inspection only now).

- R7 (2026-05-29): parallel FIX-5(a2) ∥ FIX-AUTH2.
  - FIX-AUTH2 (`24b649d`) → REVIEWER **PASS**. Both `/test` + `/test-transient` carry `require_tenant_session`; cross-tenant→403 pre-body (flip 403↔400 proven); pinned 3.12; the 7 pre-existing SSRF/DNS failures byte-identical, +4 new pass, zero regressions. **SCOPE-A fully closed.**
  - FIX-5 attempt 2 (`57d5aa5`) → REVIEWER **FAIL** (strike 2/3). Functional fix is CORRECT + LIVE: shared `singleflight.Group` created once in `newProxyHandler` (main.go:205), set `SF: h.sfGroup` on prod deps (main.go:459), coalescing genuine (50→1), race/vet/tidy clean, x/sync direct. BUT guard test illusory: `TestProductionPath_SFCoalescesOnConcurrentMiss` hand-builds `deps{SF: h.sfGroup}` itself instead of driving `handleOAuth2PasswordGrant` → FLIP-B (delete `SF:` at main.go:459, the exact attempt-1 regression) leaves all 3 guard tests GREEN. → attempt 3: rewrite the guard to exercise the real construction site so FLIP-B fails. DO NOT change the (correct) functional code. **STRIKE 2 — attempt 3 is last before hard-stop.**

## Open questions / escalations
(none open)
