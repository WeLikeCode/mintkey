# 99-report — Service-Templates Adversarial Review + Remediation

**Session:** `2026-05-28-service-templates-adversarial`
**Branch:** `feature/service-templates` (base `main`, started @ `828bd7c`)
**Status:** **COMPLETE — final full-DoD Opus review: READY TO MERGE.** 29 commits, local (not pushed).

## What happened
1. **Adversarial review (5 parallel Opus agents, read-only):** security, concurrency/correctness, contract/spec-compliance, test-quality/coverage, implementation-quality. Reports in `reviews/01..05`. Found 3 CRITICAL, 5 HIGH, 8 MEDIUM, 2 LOW + a pre-existing HIGH authz gap; 0/19 optional Kiro tasks implemented.
2. **Orchestrated remediation** (Sonnet implementers, fresh Opus reviewers per chunk, 3-strike rule): 12 fix chunks + 2 carry-over cleanups (FIX-10b, CO-7) + 7 optional-task chunks.
3. **All 19 optional Kiro test tasks** implemented (genuine PBT via `rapid`/`hypothesis`, real render + integration tests) and marked `[x]*` in `.kiro/specs/service-templates/tasks.md`.
4. **Final full-DoD Opus review:** independently re-ran all suites + spot-verified high-risk fixes → READY TO MERGE.

## Defects fixed (owner chose: fix ALL severities + SCOPE-A in-branch)
| ID | Sev | Fix | Commit |
|---|---|---|---|
| BUG-1 vault scope breaks all egress | CRIT | proxy client sends identity+token; compose provisions by default; cross-module guard test | `c58baab` (3 attempts) |
| BUG-2/9 token_url validation dead code | CRIT | wired `OAuth2PasswordGrantPayload` into create + rotate write paths | `fb86aba`,`f60f90b` |
| BUG-3/6/12/17 Go exchanger SSRF/JSONPath/timeout/error-body | CRIT/HIGH/MED | dial-time IP allowlist + no-redirect + resp-header timeout + safe extraction | `78088ba` |
| BUG-4/14 cache expiry poison + unbounded | HIGH/MED | overflow guard, past-exp reject, 24h clamp, 10k size cap | `274f2e8` |
| BUG-5 thundering herd | HIGH | shared singleflight wired in prod | `3ce81f4`,`57d5aa5`,`21763db` |
| BUG-7/16/19 UI false-success/field-map/highlight | HIGH/MED/LOW | require id on success, surface errors, align field names | `7218414` |
| BUG-8 proto descriptor missing enum 8 | HIGH | regenerated vault.pb.go via protoc-gen-go | `dcd1a82` |
| BUG-10 audit bypasses emitter, drops agent_id | MED | routed via `EmitTokenExchanged`, host-only, no leak | `1077925` |
| BUG-11 (Req 23.5) credential pre-pop missing | MED | from-template returns credential_hint; UI renders panel | `165809e` |
| BUG-13/15/18 base_url DNS SSRF / YAML junk / TOCTOU | MED/LOW | shared DNS-resolving SSRF helper, real hints, atomic 409 | `63b0a57`,`ad85753` |
| SCOPE-A cross-tenant write | HIGH (pre-existing) | `require_tenant_session` on all 6 write endpoints | `b57e3cb`,`24b649d` |

Carry-overs: FIX-10b (`a731325`) explicit NewClient + pin compose secret + delete stale test; CO-7 (`e8251ee`) dev React → 18.3.1.

## Optional tasks (all 19) — chunks
T-deps `5457eec` · T-py `24d1ac0` (2.4,3.2,3.3,3.4,5.4) · T-cache `c176471` (7.2-7.5) · T-exchanger `b270c5f` (6.2-6.5) · T-vault `665da91` (10.2) · T-egress `8811034` (9.4-9.7) · T-ui `1da2761` (12.2). Kiro marks committed `02f2ab4`,`94f212c` + within chunks.

## Verification (final reviewer, re-run independently)
- proxy-plugin `go test ./... -race` GREEN; vault-adapter GREEN; `go vet`: only pre-existing `metrics.go:110`.
- admin-api (pinned 3.12) service-templates suites 151 pass; admin-ui vitest 409 pass + 13 render; tsc 0 new errors.
- BUG-1/2/3/8/10 + SCOPE-A spot-verified live; 4 optional tasks flip-discriminating.

## Known-reds (documented pre-existing / environmental — NOT merge blockers)
- 7 `tests/integration/admin_api/test_services.py` failures — `/test`+`/test-transient` dial `*.example.com`, blocked in sandbox (DNS/SSRF). Pre-existing.
- 1 admin-ui `test_permissions.test.ts` — unrelated permissions URL assertion; no permissions files touched.
- `apps/proxy-plugin/internal/metrics/metrics.go:110` go vet `WriteTo` signature — pre-existing.
- `go mod tidy` can't fully run (go.work references non-existent `github.com/mintkey/mintkey` remote); go.mod/go.sum untouched, both modules build/race-test green.

## Follow-up (separate housekeeping ticket, optional)
Resolve the 4 environmental/pre-existing items above; consider production hardening of the dev shared proxy secret + dev SSRF KEK.

## Next step
Branch is local with 29 commits. Awaiting user authorization to push / open PR (via Mintkey proxy per project convention).
