# Public GitHub Release Readiness Matrix

| ID | Area | Finding | Severity | Status | Evidence | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|
| P0-1 | Legal | Missing root LICENSE | P0 | ⬜ | README claims Apache-2.0 | LICENSE exists and matches docs | |
| P0-2 | Security | Placeholder disclosure contact | P0 | ⬜ | SECURITY.md | Real contact or explicit owner escalation | |
| P0-3 | Contracts | OpenAPI validation fails | P0 | ⬜ | missing UnprocessableEntity response | OpenAPI validator exits 0 | |
| P0-4 | CI | Workflow YAML parse fails | P0 | ⬜ | ci.yml run scalar | Workflow YAML parser exits 0 | |
| P0-5 | CI | Release-critical checks masked | P0 | ⬜ | || true in CI/Makefile | No masking for critical gates | |
| P0-6 | Governance | CONTRIBUTING conflicts with no co-author rule | P0 | ⬜ | Co-Authored-By required | Removed from docs/examples | |
| P0-7 | Docs | Public placeholders remain | P0 | ⬜ | README/QUICKSTART/OpenAPI | No release-blocking placeholders | |
| P1-1 | Governance | Missing OSS templates | P1 | ⬜ | .github only workflows | Templates added | |
| P1-2 | Supply Chain | Missing dependency/security automation | P1 | ⬜ | no Dependabot/CodeQL/etc | Automation added or deferred | |
| P1-3 | Packaging | Missing .dockerignore | P1 | ⬜ | none found | Dockerignore coverage exists | |
| P1-4 | Containers | Runtime hardening unclear | P1 | ⬜ | Dockerfiles | Non-root or documented deferral | |
| P1-5 | Release | Version/release policy inconsistent | P1 | ⬜ | 0.1.0-experimental vs 1.0.0 | Policy coherent | |
| P1-6 | Final | Full readiness verification | P1 | ⬜ | final gates | 99-report complete | |