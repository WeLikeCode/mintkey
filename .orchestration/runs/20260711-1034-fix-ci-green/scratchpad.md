# Run: fix-ci-green (20260711-1034 UTC)

## Task
commit, merge, push `fix/admin-api-argon2-to-thread` + CI-green fixes to main; get core ci.yml green; test locally; backup first.

## User decisions
- Land: **this branch (fix/admin-api-argon2-to-thread) + CI fixes** → merge to main + push.
- CI scope: **core ci.yml gate** (10 jobs). Trivy container-scan / Playwright / scorecard = OUT OF SCOPE (flag separately).

## Plan (milestones)
- M0 (self): backup; commit uncommitted vault/client.go timeout fix; rebase branch onto origin/main.
- M1 (self, read-only): reproduce ci.yml jobs locally -> failure inventory (ground truth).
- SPEC: openspec/changes/fix-ci-green (proposal/tasks/design + deltas) from M1.
- M2 (implement primitive): fix failures (file-disjoint milestones) — sonnet + opus review + fix loop.
- M3 (verify primitive): each ci.yml job green locally, independent evidence.
- LAND (self): merge to main + push.

## Known baseline reds (to confirm in M1)
- lint-go: metrics.go:110 go vet WriteTo signature; golangci-lint injector_test.go:151 errcheck, emitter_test.go:171 errcheck, exchanger.go:500 isNetworkError unused + gosimple S1008.
- test-python-unit: test_email_services.py (TestOutlookUserinfo x4, TrimsWhitespace x5); stray src/admin_api/api/_ssh_test.py collection error.
- test-integration: "fails on main" (cause unknown — confirm in M1).

## Event log
- 20260711-1034: run created; scope confirmed; primitives contracts read.

## M1 FINDING (pivotal) — 2026-07-11
- ci.yml is GREEN on main (run 29145179287 / 7d21250): all 10 jobs success incl. Integration.
- Earlier "baseline failures" (metrics.go go vet, golangci errcheck/unused, email tests) were NOT ci failures — they came from agents running go vet/golangci INSIDE apps/proxy-plugin, which CI does not do.
- CI COVERAGE GAP: root `go list ./...` = only packages/go (0 apps pkgs). CI never vets/tests/lints proxy-plugin/broker/email-proxy/kong-syncer. Latent issues hide there.
- Branch fix/admin-api-argon2-to-thread rebased onto main = 2 new proxy commits (67e21da form-encode Exchange; 442de92 vault dial-timeout). Build+tests pass. Won't break CI.
- DECISION NEEDED: (A) just land branch (CI stays green) vs (B) close the coverage gap + fix surfaced apps issues so CI is comprehensive+green.

## REVIEW GATE 1 = REJECT (critical) — 2026-07-11
- Independent opus reviewer refuted the change: extended golangci loop goes RED (67 findings the enumeration missed due to a go-run-in-loop false-zero bug). vet/test/rename/isNetworkError/errcheck fixes all PASS.
- Authoritative (installed golangci v1.64.8 loop): email-proxy 15, kong-syncer 1, ssh-proxy 48, vault-adapter 3 = 67. broker/proxy-plugin/root = 0.
- User decision: FIX ALL 67 + full coverage. Dispatching per-module fix workflow (sonnet impl + opus review), SA9003 swallowed-errors handled properly not silenced.

## CLOSE — 2026-07-11
- Review gate 2 (per-module opus + my re-verify): PASS. All 67 golangci findings fixed; SA9003 swallowed-errors handled/logged not silenced (spot-checked ssh-proxy).
- Landed: commit 5df29ba -> force-pushed (stale remote had only superseded argon2 commits) -> PR #260 -> squash-merged to main as 13df876.
- CI on PR: 9/10 green incl. the 2 changed jobs (Lint Go, Go Unit Tests) + all lint/unit/acceptance/architecture/schema. Integration Tests (docker, unaffected) still in-progress at merge; merged per user's non-blocking-integration convention.
- OUTCOME: done. OpenSpec change openspec/changes/ci-cover-go-apps NOT archived (leave to user per orchestrate).
