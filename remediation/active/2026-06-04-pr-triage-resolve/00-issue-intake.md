# Issue intake — Mintkey PR triage and resolve (28 open PRs)

## 1. Problem statement
28 PRs are open on WeLikeCode/mintkey. Operator wants them resolved (merge / close / fix) per the standing CI gates memory: only `dependency-review` is required; Trivy/Playwright/CodeQL failures are non-required noise. Resolution order is explicit:
  1. PR #190 (author = ciprianiacobescu) — 0 checks, MERGEABLE/CLEAN. Investigate why no checks ran, then merge if appropriate.
  2. Bulk-merge 22 dependency-review-PASSING PRs.
  3. Investigate the 5 dep-review-FAILING PRs (#183 react, #182 @types/node, #181 uuid, #180 pino, #178 vitest — all admin-ui) and draft `allow-dependencies-licenses` exception patches (or recommend close).

## 2. User-visible symptom
`gh pr list --state open` returns 28 entries. Operator wants the queue drained per the order above.

## 3. Expected behavior
- #190 merged (or rationale why not).
- 22 mergeable PRs merged via merge-commit (per `project_mintkey_ci_merge_gates`).
- 5 dep-rev failures diagnosed; patch drafted to unblock; operator approves before applying.
- No regression introduced to main.

## 4. Evidence (verified 2026-06-04)
- Open PR list captured (see triage table in conversation).
- Required gate per memory: `dependency-review` only. `enforce_admins=False` so admin PUT-merge works even on "blocked" state.
- Per memory: repo merges via merge-commit. PBT deps may need `allow-dependencies-licenses` exceptions.
- 51 cached `mk_agent_…` keys all return `mintkey:auth_required` — broker dogfooding not available this session. Fallback to direct `gh` with the `gho_…` OAuth token from macOS git credential helper (`echo "url=https://github.com" | git credential fill`).

## 5. Scope
- C-1: PR #190 investigate-then-merge.
- C-2: Bulk-merge of these 22 — `#179, #177, #175, #174, #172, #170, #164, #163, #162, #159, #158` (zero failures) and `#176, #173, #171, #169, #168, #167, #166, #165, #161, #160, #157` (only non-required failures).
- C-3: Diagnose dep-rev failures on `#183, #182, #181, #180, #178`; draft `allow-dependencies-licenses` patch (do NOT merge those PRs yet — return the diff for operator review).
- Out of scope: closing any PR; bumping any version manually; modifying anything in main.

## 6. Out of scope
- Modifying main outside of merge commits.
- Closing PRs without operator confirmation.
- Touching uncommitted working-tree changes (admin-api, email-proxy, email_services.py, oauth2_authorized_ui_flag work from earlier in the session — all uncommitted and unrelated).
- Bypassing required checks via admin PUT-merge unless operator explicitly authorizes.
- The 5 admin-ui major-bump PRs MUST NOT be merged in this session — only diagnosed.

## 7. Risk level
- C-1: **LOW.** Single PR by operator; mergeable/clean.
- C-2: **MEDIUM.** 22 dependabot PRs. Mostly minor/patch; some majors (golangci-lint-action 8→9, setup-python 5→6, setup-go 5→6, codeql-action 3→4, setuptools 68→82). Even with required-pass, majors may break downstream behavior. Mitigations: merge in dependency order (Actions first, then Go modules, then Python, then Docker base images); pause between batches; if main goes red, stop immediately and roll back the last batch.
- C-3: **LOW.** Investigation only; no merges.

## 8. Verification target — Definition of Done

### C-1
- [ ] Root-cause for #190's "0 checks" identified (likely either: required workflows didn't trigger for this branch's paths; or admin previously bypassed checks).
- [ ] Decision documented: merge OR hold for CI run.
- [ ] If merged: PR #190 state is MERGED on GitHub; main branch SHA advanced; CI on main is green (or known-red pre-existing).
- [ ] Merge method = merge-commit (NOT squash, NOT rebase).
- [ ] No `Co-Authored-By: Claude` trailer on the merge commit.

### C-2
- [ ] All 22 PRs in scope are MERGED, in this order:
      Actions first (#175, #174, #177, #179, #166), then Go modules (#162, #163), then Docker base images (#157, #158, #159, #160 — only #157/#158/#159 are clean; #160 has 2 non-req failures), then Python packages (#172, #170, #164 — mintkey-models — first, then #169, #167, #173, #171, #176 — admin-api), then leftover (#165, #168, #161 — node base image).
- [ ] After each batch, check `main` CI: green or known-red-pre-existing.
- [ ] If a batch reds main, STOP and surface to operator.
- [ ] Each merge is a merge-commit, not a squash.

### C-3
- [ ] For each of #183, #182, #181, #180, #178: the failing dep-rev check log is fetched; the specific license / package triggering the failure is identified.
- [ ] A patch is drafted (likely an edit to `.github/dependency-review-config.yml` or to the workflow's `allow-dependencies-licenses` input) that would unblock the PRs.
- [ ] The patch is NOT applied; it is returned in the report for operator review.
- [ ] A recommendation per PR: "merge after license-allow", "close — semver-major risk too high for now", or "needs codebase migration before merge".

## 9. Owner decisions
- **Broker dogfooding waived for this session** — no working `mk_agent_…` key. Fall back to `gh` + OAuth token. If operator later wants to re-do via broker for audit purposes, the merges are durable in GitHub regardless.
- **Merge method = merge-commit** (per memory).
- **No `Co-Authored-By: Claude` trailers** (per global CLAUDE.md).
- **C-3 dependency-review-failing PRs**: report only; operator decides per-PR.
- **Token handling**: subagents fetch token via `git credential fill` (do NOT embed in prompts or write to long-lived files).
