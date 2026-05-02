# Kiro Project Template

> A reusable scaffolding for **specification-driven engagements** built around Kiro and Claude Code agents.
> Designed by Enterprise Business Architect Practice for greenfield architecture-led projects.

**Template version:** 0.1.0
**Last reviewed:** 2026-05-07

---

## What this is

A starter kit for new client engagements that:

- Encodes the **steering / ADR / risk-register / assumption-register / open-questions** discipline into the repo from day 0
- Forces the architect through a **bootstrap wizard** that captures the load-bearing decisions before any code is written
- Ships a curated set of **agent skills** (architecture-advisor, think-tiger, adversarial-review, spec-first-check, …) tuned to prevent vibe coding
- Implements **discipline-aware steering loading** using Kiro's three real inclusion modes (default-load / `fileMatch` / `manual`) — only the conventions relevant to a file or workflow load into context, never all of them at once
- Provides **role-based onboarding tracks** so a new joiner is productive in under a working day
- Hosts **templates** (ADR, risk register, assumption register, decision log, open questions, meeting notes) ready to populate

It is **not** a code generator. It does not prescribe a tech stack. It records the choices the architect makes and rewards the team for staying inside the discipline.

## What this is NOT

| It IS | It IS NOT |
|---|---|
| A governance scaffold | A boilerplate microservice |
| Documentation infrastructure | Customer-facing docs site |
| ADR / register / spec discipline | A test framework |
| A skills catalog for Kiro / Claude Code | A general-purpose dev container |
| Rendered defaults for ~6 archetypes | A prescription of NestJS / FastAPI / etc. |

If you're looking for a framework that picks your event bus, persistence layer, or web framework — this isn't it. This template asks the architect to make those choices and records them.

---

## Quick start (60 seconds)

```bash
# 1. Clone the template into your engagement repo
git clone <this-template> my-engagement && cd my-engagement

# 2. Run the bootstrap wizard via Kiro (reentrant — safe to re-invoke)
#    Open Kiro and say: "set up this project"  →  invokes the project-setup skill
#    Or via shell fallback:
./bootstrap/setup-wizard.sh

# 3. Verify health
make doctor

# 4. Read your role's onboarding track
open docs/onboarding/README.md
```

The wizard generates only the steering / register files justified by the answers. It refuses to proceed if mandatory questions are blank, if conflicting answers are detected, or if Q25 (top three real risks) is padded with platitudes.

## What to read next

| Role | Start here | Time |
|---|---|---|
| Anyone, first time | [BOOTSTRAP.md](BOOTSTRAP.md) | 15 min |
| Architect setting up a new engagement | [bootstrap/questionnaire.md](bootstrap/questionnaire.md) | 30 min |
| Backend dev | [docs/onboarding/backend.md](docs/onboarding/backend.md) | 2 hrs |
| Frontend dev | [docs/onboarding/frontend.md](docs/onboarding/frontend.md) | 2 hrs |
| Data / ML engineer | [docs/onboarding/data-ml.md](docs/onboarding/data-ml.md) | 2 hrs |
| TL / Engineering Manager | [docs/onboarding/lead.md](docs/onboarding/lead.md) | 90 min |
| Architect already running an engagement | [docs/onboarding/architect.md](docs/onboarding/architect.md) | 3 hrs |

If you have **15 minutes**, read this README + BOOTSTRAP.md.
If you have **1 hour**, add the questionnaire walkthrough.
If you have **half a day**, do the full onboarding track for your role.

---

## Repo map

```
{{ENGAGEMENT_NAME}}/
├── README.md                 # This file — top-level entry
├── BOOTSTRAP.md              # 15-min setup guide
├── CHANGELOG.md              # Template + engagement changelog
│
├── bootstrap/
│   ├── questionnaire.md      # The 25 questions the wizard asks
│   ├── post-setup-checklist.md
│   └── setup-wizard.sh       # The actual wizard (script)
│
├── .kiro/                    # Kiro convention layout
│   ├── steering/             # Conventions / governance / always-loaded rules
│   │   ├── STEERING-PROTOCOL.md  # 3 inclusion modes (default / fileMatch / manual)
│   │   ├── skills-catalog.md
│   │   └── rule-*.md         # Always-loaded protocol rules (default-load steering)
│   ├── skills/               # Skills — each is <name>/SKILL.md
│   │   ├── architecture-advisor/SKILL.md
│   │   ├── think-tiger/SKILL.md
│   │   ├── adversarial-review/SKILL.md
│   │   ├── spec-first-check/SKILL.md
│   │   ├── adr-from-decision/SKILL.md (+ references/)
│   │   ├── risk-register-update/SKILL.md (+ references/)
│   │   ├── assumption-validate/SKILL.md (+ references/)
│   │   └── decision-log-append/SKILL.md
│   ├── hooks/                # *.kiro.hook JSON — event-triggered automation
│   └── specs/                # Per-feature spec docs (Kiro SDD)
│
├── docs/
│   ├── architecture/         # ARCHITECT-OWNED — read-only for non-architects
│   │   ├── README.md         # Banner: ADD only, never edit existing
│   │   ├── adrs/             # ADR-0001..NNNN
│   │   ├── risk-register.md  # Generated by wizard
│   │   ├── assumption-register.md
│   │   └── open-questions.md
│   └── onboarding/           # Role-based tracks
│
├── contracts/                # SPECIFICATIONS — load-bearing for SDD
│   ├── README.md             # Authoring guide
│   ├── openapi/              # REST contracts
│   ├── asyncapi/             # Event contracts
│   ├── jsonschema/           # Reusable payload types
│   └── fixtures/             # Canonical examples (CI validates)
│
├── tests/
│   ├── contract/             # Tests against contracts/, NOT against code
│   ├── acceptance/           # Behavioral tests citing ADR / spec IDs
│   └── unit/                 # Implementation-coupled
│
├── archetypes/               # Wizard-pickable layouts (single-app, polyglot-monorepo, ...)
│
├── examples/                 # Full-fidelity reference engagements (anonymized)
│
├── tools/                    # Audit / lint / wizard scripts
│
└── team/{handle}/            # Per-person onboarding sign-offs
    └── onboarded.md
```

---

## How we work

This template enforces a small set of non-negotiables. They are encoded as default-load steering files in [`.kiro/steering/rule-*.md`](.kiro/steering/) — Kiro auto-loads them into every agent session:

1. **Architect owns governance.** ADRs, contracts, schema authoring rules, and `docs/architecture/` are the architect's responsibility. Developers implement against governance; they don't author it. ([rule](.kiro/steering/rule-role-ownership-architect-vs-developer.md))
2. **`docs/architecture/` is ADD-only.** Suggest diffs to existing files, don't apply them. ([rule](.kiro/steering/rule-architect-doc-ownership.md))
3. **No spec, no code.** Implementation requires a referenced ADR, contract, or spec. The `spec-first-check` skill enforces this. ([rule](.kiro/steering/rule-steering-load-discipline.md))
4. **Real risks, no padding.** Risks must have (a) what specifically breaks, (b) cited evidence, (c) named affected component. Speculative concerns go to the backlog, not the register. ([rule](.kiro/steering/rule-real-risks-not-padding.md))
5. **Smallest first cut.** Don't over-elaborate when a one-page artifact unblocks the team. ([rule](.kiro/steering/rule-smallest-first-cut.md))

These five rules account for ~80% of the corrections we've made on real engagements.

---

## Architectural baseline (engagement-customizable)

The template ships these as defensible defaults — the wizard records the architect's choice to keep, replace, or override:

| Pattern | Default | Override surface |
|---|---|---|
| Append-only / immutable business records | On | `data_policy.immutable_entities_default` |
| Idempotent processing with explicit idempotency keys | On | data-lifecycle steering |
| Single-writer-per-table / domain ownership of writes | On | structure steering |
| Multi-layer tenant isolation | Off (single-tenant default) | `auth.tenant_signal` |
| Schema-driven dynamic forms | Off | `ui.schema_form_lib` |
| Contract-first development with generated SDKs | On | contracts/ pattern |
| Observability-by-default (OpenTelemetry, structured logs) | On | observability steering |
| Append-only ADR / decision log | On | governance steering |

If an engagement disables any of these, the wizard records the choice as ADR-0001-bootstrap and exposes the trade-off.

---

## License

[TBD]
