# Bootstrap — From clone to "hello team" in 15 minutes

You have just cloned this template. This document gets you to a working, populated engagement.

## Audience

You are either:
- **Architect** starting a new engagement (this document is primarily for you), or
- **Joining a project** that was already bootstrapped from this template (skip to step 4)

---

## Step 0 — Prereqs (2 min)

Required:
- Git ≥ 2.30
- Bash / zsh
- `make`
- Markdown editor of choice
- Claude Code or Kiro CLI installed and authenticated

The bootstrap wizard does NOT install or pin a language toolchain. Toolchain choices are recorded by the wizard and enforced later by per-engagement CI.

---

## Step 1 — Run the wizard (5 min)

Open Kiro and say: **"set up this project"** — this invokes the `project-setup` skill.

Or via shell fallback:

```bash
./bootstrap/setup-wizard.sh
```

The wizard asks **16 mandatory + 9 optional questions**. See [bootstrap/questionnaire.md](bootstrap/questionnaire.md) for the full catalog before you start — pre-thinking the answers makes the live wizard fast.

The wizard writes:

| File | Populated from |
|---|---|
| `.kiro/steering/product.md` | Q1-Q5, Q25 |
| `.kiro/steering/architecture-principles.md` | Generic, architect-owned, ready to refine |
| `.kiro/steering/structure.md` | Q9, Q10, Q11, archetype choice |
| `.kiro/steering/tech.md` | Confirmed answers only — nothing speculative |
| `.kiro/steering/repo-governance.md` | Q15 |
| `.kiro/steering/ownership-and-codeowners-strategy.md` | Q4 |
| `.kiro/steering/open-questions.md` | Every Q-answer marked Defer / TBD |
| Conditional steering (per Q triggers) | See questionnaire |
| `docs/architecture/architecture-vision.md` | Skeleton with author = Q4 |
| `docs/architecture/risk-register.md` | Q25 — your three top risks (no AI padding) |
| `docs/architecture/assumption-register.md` | Empty register, ready for first entries |
| `CODEOWNERS` | Architect-only on `docs/architecture/` and `.kiro/steering/` |
| `.kiro/setup-state.json` | Machine-readable record of every answer and phase progress |

The wizard **refuses to proceed** if:
- Any mandatory question is blank, "skip", or whitespace-only
- Q3 (business goal) is shorter than 120 characters or matches a denylist of platitudes
- Q4 (architect) is missing a recognizable email
- Q25 (risks) yields fewer than 3 entries with both "what breaks" and "evidence"
- Conflict detected (e.g. air-gapped deployment + cloud-SaaS-only telemetry)

---

## Step 2 — Doctor check (2 min)

```bash
make doctor
```

> `make doctor` delegates to `tools/doctor.sh`. If the script doesn't exist yet for your engagement, the Makefile will report it clearly.

Verifies:
- Wizard answers file is well-formed
- All conditionally-loaded steering files exist
- ADR template applied
- Architect-only CODEOWNERS in place
- Kiro / Claude Code can read the steering protocol

Red items have a "How to fix" link in the output. Do not skip past red.

---

## Step 3 — Sanity-read what was generated (3 min)

Skim:
1. `docs/architecture/architecture-vision.md` — your scaffold; read, don't yet refine
2. `.kiro/steering/product.md` — confirms what you said about the engagement
3. `.kiro/steering/open-questions.md` — every "Defer" answer landed here
4. `docs/architecture/risk-register.md` — the three real risks you named

If any of these feels wrong, re-invoke the skill in Kiro: **"set up this project"** — it resumes from the last completed phase. Or run `./bootstrap/setup-wizard.sh --re-run`.

---

## Step 4 — Pick your role track (2 min)

Open [docs/onboarding/README.md](docs/onboarding/README.md) and follow the role card that matches you. Each card is ≤ 8 files, ≤ 2 hours.

---

## Step 5 — Sign in (1 min)

```bash
cp team/_template/onboarded.md team/{your-github-handle}/onboarded.md
```

Edit the file. Tick the gate items as you complete them. This is how the team knows you're ready for review duty.

---

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| Wizard exits "Q3 below cap" | Business goal too thin | See questionnaire.md §Q3 — write what changes for the customer |
| Wizard exits "Q25 padding" | Risks lack "what breaks" + evidence | See [.kiro/steering/rule-real-risks-not-padding.md](.kiro/steering/rule-real-risks-not-padding.md) |
| `make doctor` warns "steering file dead" | Conditional file generated but no trigger fires | Re-invoke the wizard to correct the answer, or delete the unused file |
| Claude / Kiro agent loads no steering | Frontmatter missing or invalid | Run `make audit-steering` |
| New ADR has number collision | Two architects ran `adr-from-decision` simultaneously | Resolve manually; lowest sha1 wins |

---

## What's next

Once bootstrap is clean:

1. **Author your first ADR.** Use the `/adr-from-decision` skill. It refuses to write directly to `docs/architecture/adrs/` — it drafts in `team/{handle}/drafts/` for your review first.
2. **Schedule the first risk-register update.** Use `/risk-register-update` after every meeting that surfaces new evidence.
3. **Run an `adversarial-review`** on the architecture vision once you've populated more than the wizard skeleton.
4. **Set up the CI gates.** Run `make spec-trace` and `make contract-lint` — see `tools/README.md` for what each check does.
5. **Bring your first developer onboard** — they read [docs/onboarding/README.md](docs/onboarding/README.md), pick their track, sign in via `team/{handle}/onboarded.md`.

If you cannot complete all questions in one sitting, the `project-setup` skill saves progress after each phase automatically. Re-invoke it to resume. The shell wizard also supports `./bootstrap/setup-wizard.sh --save-and-exit`.
