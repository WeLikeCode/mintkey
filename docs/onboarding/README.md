# Onboarding

> Pick the role card that matches you. Each track is ≤ 8 files, ≤ 3 hours. After you complete the track you should be ready to ship your first PR.

## Tracks

| Role | Card | Time |
|---|---|---|
| Architect (Day 0) | [architect.md](architect.md) | 3 hrs |
| Backend dev | [backend.md](backend.md) | 2 hrs |
| Frontend dev | [frontend.md](frontend.md) | 2 hrs |
| Data / ML engineer | [data-ml.md](data-ml.md) | 2 hrs |
| TL / Engineering Manager | [lead.md](lead.md) | 90 min |

## Reading roadmap

```
README.md (5 min)
    ↓
BOOTSTRAP.md (15 min)
    ↓
Pick role
    ↓
[Architect] → vision TL;DR + steering core + 3 recent ADRs + open-questions
[Backend]   → structure + lang-conventions + api-contracts + database + testing + dev-workflows
[Frontend]  → web-app-structure + frontend-conventions + ui-kit + api-contracts (consumer view) + testing
[Data/ML]   → data-lifecycle + object-storage + database + workers + observability + fixtures + security-tenancy
[TL / EM]   → repo-governance + ownership + branching-and-release + ceremonies + open-questions
    ↓
team/{handle}/onboarded.md → tick the gates
```

## After your track

1. **Sign in.** Copy `team/_template/onboarded.md` → `team/{your-handle}/onboarded.md`. Tick the gates as you complete them.
2. **First PR.** Even a typo fix. The point is to exercise the PR flow.
3. **First comment.** Leave a comment on an open ADR or open-question. Forces real engagement with the architecture.

## Continuous re-onboarding

When ADRs land or steering files change meaningfully, an entry appears in [CHANGELOG-for-humans.md](CHANGELOG-for-humans.md). Skim weekly.

## If you're stuck

- `make doctor` — local environment health check (delegates to `tools/doctor.sh`)
- [troubleshooting.md](troubleshooting.md) — common errors
- Ping your buddy (assigned during bootstrap)

## Anti-patterns this track design defeats

- "Read all 22 steering files" → no track lists more than 8 files
- 50-page architecture vision as Day-1 reading → architect track reads TL;DR + ToC only on Day 0
- Onboarding doc that rots → 90-day re-review CI job
- No "you are here" indicator → numbered table with checkbox column on every track
- Onboarding as a one-time event → CHANGELOG-for-humans + weekly digest

---

*Onboarding lives here (`docs/onboarding/`, team-owned). It links INTO `docs/architecture/` (architect-owned) but never edits it.*
