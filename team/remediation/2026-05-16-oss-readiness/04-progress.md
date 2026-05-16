# OSS Readiness — Progress Log

Append-only. Most recent entry at the top.

---

## 2026-05-16 — OSS-7 IMPLEMENTER: Marketing package

**Session:** OSS-7
**Chunk:** Marketing Package
**Status:** PASS

### Files modified

- `marketing/index.html` — full rewrite: new hero headline ("Self-hosted credential broker for AI agents. / Agents get scoped short-lived access. They never see raw API keys."), sub-headline, top-of-page pre-alpha banner, 4 CTA buttons (Try locally → GitHub quick-start anchor, Read security model → security.html, View architecture → architecture.html, Contribute → GitHub CONTRIBUTING.md), "Why now / Who it is for" section (4 paragraphs), alternatives-comparison table (6-row: env vars / Vault / API gateway / secrets manager / agent runtime / Mintkey), supported auth schemes table (verified against vault.proto + openapi.yaml: 4 shipped, 2 partial, 3 not shipped), footer links upgraded to absolute GitHub URLs for SECURITY.md and CONTRIBUTING.md.
- `marketing/architecture.html` — added pre-alpha banner at top; footer links for SECURITY.md and CONTRIBUTING.md upgraded to absolute GitHub URLs; footer pre-alpha warning text strengthened.
- `marketing/security.html` — added pre-alpha banner at top; security disclosure email (`mailto:the+security@ciprianiacobescu.com`) added to Reporting section; SECURITY.md read-source link upgraded to absolute GitHub URL; footer links upgraded to absolute GitHub URLs.
- `team/remediation/2026-05-16-oss-readiness/02-matrix.md` — F-32 and F-33 flipped ⬜ → ✅ with verification commands.

### Auth scheme verification

Compared `docs/architecture/contracts/vault-adapter/vault.proto` (AuthScheme enum) and `docs/architecture/contracts/rest/openapi.yaml` (AuthScheme enum):

| Scheme | Proto | OpenAPI | Claimed in marketing |
|---|---|---|---|
| api_key_header | AUTH_SCHEME_API_KEY_HEADER=1 | present | ✓ Shipped |
| api_key_query | AUTH_SCHEME_API_KEY_QUERY=2 | present | ✓ Shipped |
| bearer_token | AUTH_SCHEME_BEARER_TOKEN=3 | present | ✓ Shipped |
| basic_auth | AUTH_SCHEME_BASIC_AUTH=4 | present | ✓ Shipped |
| oauth2_client_credentials | AUTH_SCHEME_OAUTH2_CLIENT_CREDENTIALS=5 | present | Partial |
| oidc_client_secret | AUTH_SCHEME_OIDC_CLIENT_SECRET=6 | present | Partial (operator IdP only) |
| mtls | AUTH_SCHEME_MTLS=7 | absent (proto only) | Not shipped |
| AWS SigV4 / GCP IAM | absent | absent | Not shipped |
| OAuth 2.0 user-delegated | absent | absent | Not shipped |

No overclaiming: every "Shipped" entry is in both proto and OpenAPI enum. Partial and Not-shipped entries are flagged accurately.

### Verification (run in /Users/alexandruiacobescu/gooseProjects/mintkey)

```
grep -c -i 'pre-alpha\|not for production' marketing/index.html marketing/architecture.html marketing/security.html
# → index.html:4, architecture.html:2, security.html:3 (all ≥1)

grep -c -E 'Try locally|Read security|View architecture|Contribute' marketing/index.html
# → 4

grep -c -E 'env vars|API gateway|secrets manager|agent runtime' marketing/index.html
# → 4 (≥3 required)

grep -c -E 'API key|Bearer|Basic|OAuth' marketing/index.html
# → 4 (≥4 required)

rg -n '<repo-url>|TODO|placeholder|TBD|example.invalid' marketing/
# → empty

grep -i 'Self-hosted\|credential broker\|brokered\|short-lived' marketing/index.html
# → multiple matches

grep 'mailto:the+security@ciprianiacobescu.com' marketing/security.html
# → 1 match

python3 HTML parse → all 3 files OK
```

---

## 2026-05-16 — Session opened

Session directory created: `team/remediation/2026-05-16-oss-readiness/`

**Pre-existing working-tree state (NOT introduced by this session):**
```
 M grafana/provisioning/datasources/prometheus.yaml
 M otel-collector-config.yaml
?? .agents/
?? .codex/
?? .kiro/specs/grafana-request-monitoring/
?? admin-ui/e2e/tests/99-runbook-ui-verify.spec.ts
?? admin-ui/screenshots-chunk-g/
?? admin-ui/screenshots-verify/
?? grafana/provisioning/dashboards/request-monitoring.json
?? tests/unit/test_dashboard_json.py
?? tests/unit/test_otel_collector_config.py
```

This is unrelated background work (a grafana-request-monitoring spec). Logged here so reviewers can disambiguate session-introduced changes from pre-existing churn. The OSS-readiness chunks touch mostly disjoint files; collisions will be flagged if they arise.

Driver skill: `remediation-orchestrator` (~/.claude/skills/remediation-orchestrator/SKILL.md).

Next: dispatch Phase 0 researcher.

---

## 2026-05-16 — OSS-3 IMPLEMENTER: CI gates + security automation

**Session:** OSS-3
**Chunk:** CI Gates And Security Automation

### Files created
- `.github/workflows/codeql.yml` — CodeQL matrix scan (python, javascript-typescript, go); PR+push+Mon schedule
- `.github/workflows/dependency-review.yml` — dependency-review-action@v4; fail on moderate+; Apache-2.0 license policy
- `.github/workflows/container-scan.yml` — Trivy scan on 10 images; fail on HIGH/CRITICAL; SARIF upload
- `.github/workflows/scorecard.yml` — OpenSSF Scorecard; push to main + Wed schedule
- `.github/dependabot.yml` — covers github-actions, docker (10 dirs), pip (3 dirs), npm (admin-ui), gomod (4 dirs); weekly Monday; grouped minor+patch; limit 5 PRs

### Files modified
- `.github/workflows/ci.yml` — removed `|| true` mask on Mermaid render gate (line 171); gate is now blocking; inline comment explains remediation
- `Makefile` — removed all 5 `|| true` masks from `lint-python` target (ruff×3 + mypy×2); lint failures now propagate exit codes

### `make lint` exit-code finding (pre-existing issue — NOT introduced by OSS-3)

```
$ make lint
Makefile:15: *** multiple target patterns.  Stop.
exit=2
```

**Root cause:** GNU Make 3.81 (macOS) does not support colons in `.PHONY` target names
(`test:e2e test:e2e:headed test:e2e:ci`). This failure existed identically before OSS-3
changes (verified by `git stash` + `make lint` → same exit=2 on the pre-OSS-3 tree).
The OSS-3 `|| true` removal is NOT the cause.

**Direct lint status (linters invoked without make):**
- `uv run ruff check src/` in admin-api → exit 0
- `uv run ruff check src/` in mcp-server → exit 0
- `uv run mypy --strict src/admin_api/` in admin-api → exit 0
- mintkey-models: `uv sync` fails locally (setuptools.backends missing in system Python 3.9) — environment issue, not a code lint failure; CI uses `astral-sh/setup-uv@v3` which provides a correct env

**Follow-up needed (separate chunk):** Fix `.PHONY` colon-target compatibility for GNU Make 3.x
(convert `test:e2e` → `test-e2e` or use `.PHONY` workaround). This is a pre-existing
issue blocking local `make lint` but does NOT affect CI (GitHub Actions uses ubuntu-latest
which ships GNU Make 4.x where this is not a problem).
