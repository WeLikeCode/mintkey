# Service-Templates Branch — Adversarial Review: Consolidated Findings + Issue Intake

**Session:** `2026-05-28-service-templates-adversarial`
**Branch under review:** `feature/service-templates` @ `828bd7c` ("feat: implement service templates + OAuth2 password grant auth scheme")
**Base:** `main`
**Diff:** 32 files, ~5002 insertions / 189 deletions.
**Review method:** 5 parallel Opus adversarial subagents (read-only). Reports in `reviews/01..05-*.md`.

---

## 1. Issue intake (9-field gate)

1. **Problem statement.** A large feature branch (service-template catalog + OAuth2 Password Grant credential exchange) was implemented and self-marked complete in the Kiro spec, but never adversarially reviewed. Deep review found integration-breaking, security-critical, and correctness defects, plus all 19 optional test tasks unimplemented.
2. **User-visible symptom.** (a) Per static analysis, **all proxy egress returns 502** on this branch (vault scope interceptor vs. client wiring mismatch). (b) Tenant-controlled SSRF primitive executed by the proxy. (c) UI shows green "success" on failed service creation.
3. **Expected behavior.** Egress works; `token_url`/`base_url` SSRF-validated at write AND at exchange; tokens cached with correct expiry; audit complete + redacted; UI reflects real outcome; the 12 design Properties hold; optional test tasks (`[ ]*`) implemented and Kiro spec updated.
4. **Evidence.** `reviews/01-security.md`, `02-concurrency.md`, `03-contract.md`, `04-tests.md`, `05-implementation.md`. Baseline: Go 46 + vault 33 tests PASS; Python 61 PASS (correct venv). `go test -race` clean on cache.
5. **Scope.** Bugs introduced/touched by this branch + implement the 19 optional Kiro test tasks + mark them `[x]*` on completion.
6. **Out of scope (proposed, pending owner decision).** Pre-existing platform authz posture (CSRF-only writes, no session→tenant binding) — see SCOPE-A below.
7. **Risk level.** HIGH — credential broker; SSRF + egress-breaking + cross-tenant surface.
8. **Verification target (DoD).** All CRITICAL/HIGH fixed with test-first reproduction; Go `go test ./... -race` green in proxy-plugin + vault-adapter; Python service-templates tests green under pinned venv; chosen optional tasks implemented with real (non-tautological) assertions + PBT deps wired; Kiro `tasks.md` updated; final fresh-Opus review PASS.
9. **Owner decisions needed.** SCOPE-A (pre-existing authz), SCOPE-B (MEDIUM/LOW depth this round), SCOPE-C (optional-task breadth + new PBT deps), SCOPE-D (proto regen toolchain).

---

## 2. Consolidated defect list (deduplicated across 5 agents)

Confidence: **C**=Confirmed (code-traced), **L**=Likely, **S**=Suspected. "Agents" = which lenses flagged it (corroboration ⇒ higher confidence).

### CRITICAL
- **BUG-1 [C] Vault scope interceptor breaks ALL proxy egress.** New `scopeInterceptor` on vault-adapter requires `vault.read` via `x-mintkey-service-identity` header + scoped token (`apps/vault-adapter/internal/server/grpc.go:62,222`), but the proxy builds its vault client with an **empty** token (`apps/proxy-plugin/cmd/proxy-plugin/main.go:79`) and the client never sends the identity header (`apps/proxy-plugin/.../vault/client.go:94`). ⇒ every `GetCredential` → `PERMISSION_DENIED` → 502 for classic AND OAuth2 egress. Unit tests miss it (round-trip harness registers server with no interceptor). _Agents: concurrency, implementation._ **Must reproduce with an interceptor-on integration test before fixing.**
- **BUG-2 [C] SSRF: `token_url` write-time validation is dead code (Python).** `OAuth2PasswordGrantPayload` / `validate_token_url_ssrf` exist (`apps/admin-api/src/admin_api/services/credential_service.py:38,103,142`) but are never imported/called; the real credential write path stores the JSON blob verbatim. Design's "validated at write" invariant is false. _Agents: security, implementation, contract._
- **BUG-3 [C] SSRF: proxy token exchange has no IP allowlist and follows redirects (Go).** `apps/proxy-plugin/internal/credential/exchanger.go:66-117` — `http.Client` with no `CheckRedirect`, no dial-time IP allowlist ⇒ reaches `169.254.169.254`/loopback/internal via stored URL, redirect, or DNS-rebind. _Agents: security._ Defense-in-depth required even after BUG-2.

### HIGH
- **BUG-4 [C] `DetermineExpiry` poisons the cache.** (a) `time.Duration(expiresIn)*time.Second` overflows for `expires_in` ≳ 9.2e9 → negative duration → past `ExpiresAt` (`token_cache.go:129`); (b) JWT `exp` in the past cached verbatim, no clamp (`token_cache.go:139`); (c) unverified far-future `exp` pins a stale/revoked token for process lifetime. ⇒ re-exchange storm / dead graceful-degradation. _Agents: security, concurrency._
- **BUG-5 [C] No singleflight on cache miss → thundering herd.** `oauth2_handler.go:92-147` — N concurrent requests for the same (tenant,service) on a cold/expired entry fire N simultaneous token exchanges. Cost / rate-limit / credential-lockout amplifier. _Agents: concurrency._
- **BUG-6 [C] JSONPath extraction unsafe over hostile JSON.** `exchanger.go:155-200` — tenant-controlled path, full unmarshal into `any`, no depth/segment cap; numeric token rendered via `%v` (sci-notation/precision loss) → corrupted Bearer; object-only, no array indexing. _Agents: security, implementation._
- **BUG-7 [C] React false-success + masked errors.** `ServiceTemplatePicker.tsx:259-275` + `services.ts:348` (`resp.json().catch(()=>({}))`): a 2xx with no `id` shows the green success banner; BFF (`services.ts:233-251`) masks upstream `/v1/service-templates` failures as an empty list ("No templates available"). _Agents: implementation._
- **BUG-8 [C] Generated `vault.pb.go` not regenerated.** Proto source adds value 8 and the Go const agrees, but `packages/go/vault/v1/vault.pb.go` only got a 3-line hand edit — the embedded `file_vault_proto_rawDesc` still lists enum 0–7, so value 8's NAME is absent ⇒ protoreflect/protojson-by-name/gRPC-reflection don't know it exists (int32 wire path masks it). Fix = re-run codegen, not hand-edit. _Agents: contract._
- **BUG-9 [C] Python `OAuth2PasswordGrantPayload` validation not wired** (same root as BUG-2; tracked together).

### MEDIUM
- **BUG-10 [C] `token.exchanged` emitted via divergent hand-built path** that drops `agent_id` and bypasses the emitter's redaction guardrails; `emitter.go` `EmitTokenExchanged`/`EmitHit` are dead code (`main.go:457-471` vs `emitter.go:91-212`). _Agents: contract, implementation._
- **BUG-11 [C] Req 23.5 credential pre-population missing.** `create_service_from_template` (`api/services.py:464-621`) never reads `template.credential_hint`; UI declares `credential_hint` but never renders/uses it. _Agents: contract, implementation._
- **BUG-12 [C] No response-header timeout on exchanger** (only 10s whole-request `Timeout`) `exchanger.go:66` — slow `token_url` holds goroutine+conn ~10s; compounds BUG-5.
- **BUG-13 [M] `base_url` SSRF checks IP literals only**, DNS names pass `credential_service`/services validation. _Agents: security._
- **BUG-14 [C] Unbounded token cache** → memory DoS (no eviction/size cap). _Agents: security, concurrency._
- **BUG-15 [C] YAML `credential_hint` placeholder junk** (`field: value`) shipped in ~11 templates' `service_templates.yaml`. _Agents: implementation._
- **BUG-16 [C] Legacy prefill field-name mismatch:** admin-api emits `auth_type`/`openapi_spec_url`; UI `template-detail` path expects `auth_scheme`/`openapi_url` (`services.ts:288-297`) → silently drops auth type + OpenAPI URL. _Agents: implementation._
- **BUG-17 [M] `MINTKEY_SSRF_ALLOW_PRIVATE` global kill switch** + `%s`-into-JSON 502 error body (latent) `exchanger.go`. _Agents: security._

### LOW
- **BUG-18 [C] from-template 409 dup check non-atomic** (TOCTOU vs `uq_services_tenant_slug`) — should catch IntegrityError. _Agents: contract._
- **BUG-19 [C] Selected-card highlight matches on `name` fallback** (`ServiceTemplatePicker.tsx:449-450`).
- **TEST-INFRA [C] Interpreter trap:** documented `uv run pytest` resolves to anaconda Python 3.9.7 here → `str | None` annotations error but **exit 0** (misleading green). DoD must pin `apps/admin-api/.venv/bin/python -m pytest`. _Agents: tests._

### SCOPE DECISION (NOT auto-fixed)
- **SCOPE-A [HIGH, pre-existing] Platform authz posture.** Write endpoints gated only by double-submit CSRF; `from-template` reads `tenant_id` from the path with no session→tenant binding ⇒ cross-tenant create/credential write, and makes the SSRF reachable without real auth. Security agent notes this is **pre-existing** (all write endpoints share it), not introduced by this branch. Decision: fix now / separate security ticket / out of scope.

---

## 3. Optional-task coverage (Kiro `tasks.md` `[ ]*`) — 0 COVERED / 9 PARTIAL / 10 ABSENT

PBT deps absent from the repo: `pgregory.net/rapid` (Go go.mod) and `hypothesis` (Python pyproject) — must be added before any PBT task.

- **ABSENT (10):** 2.4, 3.2, 3.3, 3.4, 6.2, 6.3, 6.4, 6.5, 9.7, 12.2
- **PARTIAL (9):** 5.4, 7.2, 7.3, 7.4, 7.5, 9.4, 9.5, 9.6, 10.2 (example-based scaffolding exists in the right files; need `rapid`/`hypothesis` cases added, not replaced)
- Existing-test anti-patterns to fix: UI "tests" grep source as a string (12.2 not really covered); Property 12 reduced to a JSON-tag name check; near-tautological latency assertion (`> -1`).

Full per-task matrix with target files + exact missing assertions: `reviews/04-tests.md`.

---

## 4. Proposed chunking (for the implementation phase — Sonnet implementers, fresh Opus reviewers)

**Wave F (fixes, severity-ordered; file ownership noted for parallelism):**
- FIX-1 BUG-1 egress/scope (Go: `main.go`, `vault/client.go`) — reproduce-first. _Blocks runtime._
- FIX-2 BUG-2/BUG-9 Python SSRF wiring (`credential_service.py` + write path)
- FIX-3 BUG-3/6/12/17 exchanger hardening (`exchanger.go`) — single-file chunk
- FIX-4 BUG-4/14 cache expiry clamp + bound (`token_cache.go`) — single-file chunk
- FIX-5 BUG-5 singleflight (`oauth2_handler.go`)
- FIX-6 BUG-10 audit routing (`main.go`, `emitter.go`) — serialize after FIX-1 (shares main.go)
- FIX-7 BUG-8 proto regen (`vault.pb.go`) — needs buf/protoc (SCOPE-D)
- FIX-8 BUG-7/16/19 UI (`ServiceTemplatePicker.tsx`, `services.ts`)
- FIX-9 BUG-11 credential pre-pop (`api/services.py`, UI) — serialize after FIX-8 (shares UI)
- FIX-10 BUG-13/15/18 cleanup (YAML, base_url DNS, TOCTOU)

**Wave T (optional tasks):**
- T-deps-go (rapid), T-deps-py (hypothesis)
- T-cache (7.2–7.5), T-exchanger (6.2–6.5), T-egress/audit (9.4–9.7), T-vault (10.2)
- T-py-registry/payload (2.4, 3.2–3.4, 5.4), T-ui (12.2)

Each chunk: test-first where applicable, surgical, validated via tools, reviewed by a fresh Opus reviewer; FAIL → new implementer; 3-strike hard-stop.
