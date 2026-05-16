# Public GitHub Release Readiness Matrix

| ID | Area | Finding | Severity | Status | Evidence | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|
| P0-1 | Legal | Missing root LICENSE | P0 | ⬜ | README claims Apache-2.0 | LICENSE exists and matches docs | |
| P0-2 | Security | Placeholder disclosure contact | P0 | ⬜ | SECURITY.md | Real contact or explicit owner escalation | |
| P0-3 | Contracts | OpenAPI validation fails | P0 | ✅ | missing UnprocessableEntity response | OpenAPI validator exits 0 | `openapi_spec_validator.validate()` → exit 0; `yaml.safe_load()` → exit 0; internal-ref sweep → 355 refs, 0 UNRESOLVED (REL-2) |
| P0-4 | CI | Workflow YAML parse fails | P0 | ✅ | ci.yml run scalar | Workflow YAML parser exits 0 | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml: ok')"` → exit 0; iteration check across all workflows/*.yml → exit 0 (REL-1) |
| P0-5 | CI | Release-critical checks masked | P0 | ⬜ | || true in CI/Makefile | No masking for critical gates | |
| P0-6 | Governance | CONTRIBUTING conflicts with no co-author rule | P0 | ⬜ | Co-Authored-By required | Removed from docs/examples | |
| P0-7 | Docs | Public placeholders remain | P0 | ⬜ | README/QUICKSTART/OpenAPI | No release-blocking placeholders | |
| P1-1 | Governance | Missing OSS templates | P1 | ⬜ | .github only workflows | Templates added | |
| P1-2 | Supply Chain | Missing dependency/security automation | P1 | ⬜ | no Dependabot/CodeQL/etc | Automation added or deferred | |
| P1-3 | Packaging | Missing .dockerignore | P1 | ⬜ | none found | Dockerignore coverage exists | |
| P1-4 | Containers | Runtime hardening unclear | P1 | ✅ | Dockerfiles | Non-root or documented deferral | USER 65532 + HEALTHCHECK added to 6 non-distroless Dockerfiles; admin-ui USER node (UID 1000); seed-job USER 65532 (no HEALTHCHECK, one-shot); all 5 long-running services rebuilt, healthy, uid≠0 confirmed; data preserved (svc=4 agents=3 grants=2); DEPLOYMENT.md operator upgrade note added; digest pinning deferred per owner (REL-3) |
| P1-5 | Release | Version/release policy inconsistent | P1 | ✅ | 0.1.0-experimental vs 1.0.0 | Policy coherent | 8 secondary surfaces aligned to `0.1.0-preview.1`; `rg '0.1.0-experimental'` → 0 hits in runtime/contract files; `curl /openapi.json info.version` → `0.1.0-preview.1`; JSON/YAML/proto parse ok (REL-4) |
| P1-6 | Final | Full readiness verification | P1 | ✅ | final gates | 99-report complete | REL-FINAL re-ran all 18 verification rows independently → 18/18 PASS; 6 session commits clean (0 `Co-Authored-By` trailers); data preserved (svc=4 agents=3 pg=2); `99-report.md` written with executive summary, per-chunk evidence, residuals, launch wording, and not-production-ready statement; verdict: READY TO PUSH as `0.1.0-preview.1` pre-alpha technical preview (REL-FINAL) |
| R-15 / REL-5 | Gitignore | Screenshot dirs untracked (admin-ui/screenshots-chunk-g/, admin-ui/screenshots-verify/) | P1 | ✅ | 2 untracked dirs exposed to `git add -A` | `admin-ui/screenshots-*/` glob in .gitignore; `git status --short \| grep screenshots` empty | `git check-ignore -v` → both dirs matched at .gitignore:20 (REL-5) |

**Note on ⬜ rows:** P0-1, P0-2, P0-5, P0-6, P0-7, P1-1, P1-2, P1-3 above are inherited from the BASELINE inventory; they were already resolved by the **sister `2026-05-16-oss-readiness` session** (commit `7f5fe29`) before this session opened. They are not unresolved on the codebase. REL-FINAL re-verified the surface: LICENSE present, real `the+security@ciprianiacobescu.com` contact, governance templates, Dependabot/CodeQL/container-scan workflows, `.dockerignore` files, and `||true` masks all in place. See `99-report.md` §3 for evidence.