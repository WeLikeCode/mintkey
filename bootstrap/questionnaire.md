# Bootstrap Questionnaire

The wizard asks these questions in order. Q1-Q16 and Q25 are mandatory; Q17-Q24 are optional.

The wizard refuses to proceed if mandatory answers are missing, blank, "skip", platitude-only, or in conflict.

---

## Mandatory

### Q1. Project codename
- **Type:** free text, kebab-case, no client name
- **Populates:** `product.md` header, repo metadata, all file frontmatter
- **Why:** stable identifier across docs; avoids leaking client into open artifacts.
- **Refusal:** blank or contains client name from Q2.

### Q2. Client / sponsoring organisation
- **Type:** free text
- **Populates:** `product.md` (private "internal-only" subsection), CODEOWNERS preamble
- **Why:** distinguishes engagement; gates regulated-industry follow-ups.

### Q3. Business goal — one paragraph
- **Type:** free text, ≥ 120 characters
- **Populates:** `product.md` "Why" section, architecture-vision skeleton
- **Refusal:** shorter than 120 characters, or matches denylist of platitudes — `transform the business`, `leverage AI`, `drive value`, `synergy`, `next generation`, `digital transformation`, `unlock potential`, `enable scale`. Each must include a concrete object: what changes for the customer when this ships.

### Q4. Architect of record
- **Type:** free text — "Full Name <email>"
- **Populates:** `architecture-vision.md` author block, CODEOWNERS for `docs/architecture/`, ADR template author
- **Refusal:** missing recognizable email; "TBD" not allowed (the architect must be named on day 0 per the architect-vs-developer ownership rule).

### Q5. Engagement phase at start
- **Type:** single choice — `Discovery | PoC | MVP | Scale-up | Sustain`
- **Populates:** `product.md`, default sprint horizon, refusal sensitivity
- **Why:** drives doc depth and the wizard's tolerance for `[TBD]` answers. PoC tolerates more deferrals than Scale-up.

### Q6. Regulated industry
- **Type:** single choice — `No | Light (privacy only) | Heavy (sector regs — healthcare, finance, aviation, defense)`
- **Populates:** loads `security-and-tenancy.md`, `data-lifecycle-and-idempotency.md`, threat-model stub
- **Why:** determines tenancy / audit / retention defaults.

### Q7. Tenancy model
- **Type:** single choice — `Single-tenant | Multi-tenant shared | Multi-tenant isolated | Customer-deployed`
- **Populates:** `security-and-tenancy.md`, `structure.md`
- **Why:** drives auth / identity sections and deployment topology.

### Q8. Target deployment
- **Type:** multi-choice — `Public cloud | Private cloud | On-prem customer | Air-gapped | Hybrid`
- **Populates:** `tech.md` deployment section, `observability-and-operations.md`, `repo-governance.md`
- **Why:** air-gapped / on-prem changes telemetry, registry access, secret stores.

### Q9. Primary backend language(s)
- **Type:** multi-choice — `Python | TypeScript-Node | Java | Go | .NET | Rust | Other (specify)`
- **Populates:** loads matching `*-conventions.md` files, sets linter defaults
- **Why:** language-conventions files are gated.

### Q10. Frontend present
- **Type:** single choice — `None | SPA | SSR | Mobile | Multiple`
- **Populates:** loads `frontend-conventions.md`, `web-app-structure.md` (or omits)
- **Why:** don't pollute backend-only repos.

### Q11. Persistence primaries
- **Type:** multi-choice — `Relational | Document | Object store | Time-series | Graph | Vector | None-yet`
- **Populates:** `database-conventions.md`, `object-storage-conventions.md`, migration-tool default
- **Why:** load via `fileMatch` only when DB code is touched; no DB convention doc generated at all if there's no DB.

### Q12. API contract format
- **Type:** multi-choice — `OpenAPI | gRPC | GraphQL | Async-only | Internal-only`
- **Populates:** `api-contracts-and-schemas.md` mode flag, `contracts/` substructure
- **Why:** controls contract-first toolchain.

### Q13. AI / ML in critical path
- **Type:** single choice — `No | Sync inference | Async / batch inference | Both`
- **Populates:** loads `ai-engine-integration-flow.md` stub, `data-lifecycle-and-idempotency.md`
- **Why:** async needs queues / idempotency; sync doesn't.

### Q14. Eventing / async needed
- **Type:** single choice — `No | Yes — broker not chosen | Yes — broker chosen (specify)`
- **Populates:** `tech.md` event bus section. If "not chosen", logs as open question (refusal-soft).
- **Why:** don't bake a tech that hasn't been decided.

### Q15. Source control + branching model
- **Type:** single choice — `Trunk-based | GitFlow | GitHub Flow | Custom (specify)`
- **Populates:** `branching-and-release.md`
- **Why:** sets release cadence and PR rules.

### Q16. Architect's first-cut horizon for steering depth
- **Type:** single choice — `Skeleton (Discovery) | Working set (PoC) | Full (pre-MVP)`
- **Populates:** gates which steering files are scaffolded vs deferred
- **Why:** smallest-first-cut rule. Skeleton means skeleton.

### Q25. Three top business risks the architect already sees
- **Type:** free text — exactly 3 entries, each with `what breaks` + `evidence` fields
- **Populates:** `docs/architecture/risk-register.md` seed
- **Refusal:** fewer than 3 entries, or any entry omits `what breaks` or `evidence`. This forces real risks Day 0 and prevents AI-padded speculative risks later (real-risks-not-padding rule).

### Q26. Business Analyst artifacts available for ingestion
- **Type:** multi-choice — `Requirements doc (Word/PDF) | User stories (Jira/CSV export) | Meeting notes (MD) | Process maps (BPMN/Mermaid) | Wireframes/mockups | None yet`
- **Populates:** `docs/requirements/requirements.csv` seed, `docs/requirements/sources/` manifest
- **Why:** BA work often pre-dates the architect's engagement. Capturing what already exists prevents re-discovery and ensures traceability from BA artifacts → architectural requirements → implementation tasks. The agent can ingest these and extract requirements into the canonical CSV tracker.
- **Follow-up:** If any option other than "None yet" is selected, the wizard asks: "Provide the path(s) or paste the content. The `requirements-extract` skill will deduplicate and load them into `docs/requirements/requirements.csv`."
- **Refusal:** "None yet" is acceptable at Discovery phase. At PoC or later, warn: "No BA artifacts at this phase is unusual — confirm this is intentional."

---

## Optional

### Q17. Observability stack preference
- **Type:** single choice — `OpenTelemetry default | Vendor-specified (specify) | Defer`
- **Populates:** `observability-and-operations.md`

### Q18. Identity provider / auth pattern
- **Type:** single choice — `OIDC external (specify IdP) | Internal | API-key only | Defer`
- **Populates:** `security-and-tenancy.md`

### Q19. Schema-driven UI (forms generated from schemas)
- **Type:** Yes / No
- **Populates:** `frontend-conventions.md`, `api-contracts-and-schemas.md` cross-link
- **Why:** loads JSON-Schema renderer guidance only if Yes.

### Q20. Geospatial / heavy-data plane
- **Type:** Yes / No
- **Populates:** adds `geospatial-conventions.md` (otherwise omitted)
- **Why:** niche; never load by default.

### Q21. CODEOWNERS model
- **Type:** single choice — `Squad-aligned | Domain-aligned | Architect-only initial`
- **Populates:** `ownership-and-codeowners-strategy.md`
- **Why:** defaults to architect-only for Day 0.

### Q22. Test-data strategy known
- **Type:** single choice — `Synthetic | Anonymized prod | Customer-supplied | Defer`
- **Populates:** `fixtures-and-test-data-strategy.md`

### Q23. Known compliance frameworks
- **Type:** multi-or-none — `SOC2 | ISO27001 | HIPAA | GDPR | PCI-DSS | sector-specific (specify) | None`
- **Populates:** `security-and-tenancy.md` compliance section
- **Conditional:** only asked if Q6 ≠ "No".

### Q24. Initial squad count + names (or unknown)
- **Type:** free text
- **Populates:** `ownership-and-codeowners-strategy.md` placeholder
- **Why:** often unknown Day 0; record as TBD.

---

## After the wizard

The wizard prints a summary of:

- Files generated (with size)
- Files NOT generated and why (e.g., "frontend-conventions.md skipped: Q10=None")
- TBD answers logged to `open-questions.md`
- Manifest pinned to template version

Re-running is supported. The wizard preserves prior answers and shows a diff before overwriting.

## Anti-patterns (the wizard refuses)

The wizard MUST NOT:
1. Load all 22 steering files by default.
2. Bake tech choices that weren't answered.
3. Use placeholder names like "Acme Corp", "John Doe", "example@example.com".
4. Auto-generate risks beyond Q25.
5. Assign ownership to "Dev TL" or "Squad Lead" for any architecture-level file.
6. Write a 13-section spec when Q16 = Skeleton.
7. Cite or link to other client engagements.
8. Skip the architect-owned banner on `docs/architecture/`.
