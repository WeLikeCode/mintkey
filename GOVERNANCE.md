# Governance

This document describes how Mintkey is governed during the **pre-alpha phase**.
It will evolve as the project matures and additional maintainers join.

---

## Maintainer model

Mintkey is currently a **single-maintainer project**. The project owner holds
full decision authority over architecture, roadmap, and merge rights.

- **Project owner:** Ciprian Iacobescu (`the+security@ciprianiacobescu.com`)
- **Roadmap source of truth:** `team/remediation/` session plans and
  `.kiro/specs/` feature specs
- **Architecture source of truth:** `docs/architecture/` (20 ADRs, 18
  Accepted; the ADR list is the settled architecture)

There is no steering committee, no technical committee, and no governance board
at this stage. This is intentional for pre-alpha velocity.

---

## Decision process

### Architectural decisions — ADRs

Every architectural decision is recorded as an ADR (Architecture Decision
Record) under `docs/architecture/01-architecture/adr/0NNN-<kebab-name>.md`
using the Nygard format.

- **Accepted ADRs are immutable.** You cannot edit an accepted ADR to make
  existing code conform to it. Changes to decisions are recorded in new ADRs
  that supersede or amend the old (corrigenda pattern — see ADR-0014 as an
  example).
- **Proposals precede ADRs.** A change that requires an architectural decision
  starts as a proposal (`docs/architecture/proposal/P-NNN-*.md`), is discussed,
  and becomes an ADR once accepted.
- **ADRs precede code.** No architectural decision may be silently encoded in
  code without a corresponding accepted ADR.

### Code decisions — PRs

Non-architectural changes (bug fixes, documentation, dependency bumps, typo
fixes) are decided via pull request review. See [`CONTRIBUTING.md`](CONTRIBUTING.md)
for the full engineering checklist.

### Multi-chunk remediation work — orchestrator pattern

Large remediation sessions (e.g., OSS readiness, security hardening) use the
`remediation-orchestrator` skill. Work is broken into numbered chunks
(`OSS-1` … `OSS-8`), each owned by a single implementer agent, verified
independently, and committed separately. The orchestrator reviews each chunk
before dispatching the next wave.

---

## Proposing changes

The standard path for any non-trivial change:

1. **Open question** — add to `docs/architecture/01-architecture/open-questions.md`
   if you are uncertain whether the change warrants a full proposal.
2. **Discussion** — raise in [GitHub Discussions](https://github.com/WeLikeCode/mintkey/discussions)
   or as a GitHub issue using the feature request template.
3. **Proposal** — write `docs/architecture/proposal/P-NNN-<title>.md` following
   the existing proposal format for architectural changes.
4. **ADR** — once the proposal is accepted, the project owner elevates it to an
   ADR with `Status: Accepted`.
5. **PR** — implement against the accepted ADR, with a failing test before the
   implementation and verification output in the PR description.

Skipping steps is not allowed. See `CONTRIBUTING.md` §"The Kiro Spec-Driven
Development pipeline".

---

## Code standards

All contributors (human and AI-assisted) must follow the rules in
[`CONTRIBUTING.md`](CONTRIBUTING.md). The non-negotiable rules include:

- Spec-driven development: every change traces to a `.kiro/specs/` AC.
- ADR-first: every architectural decision has an ADR before the code.
- Contract-first: wire shape changes live in `openapi.yaml` / `vault.proto` /
  `tools.yaml` before the handler.
- TDD: failing test before implementation.
- Audit trail: every state change emits an audit event.
- Verification: PRs paste runner output and exit codes.

**Absolute prohibitions (no exceptions, no bypass):**

- `--no-verify` on commits is forbidden.
- Bypassing CI gates is forbidden.
- Weakening or removing tests is forbidden.
- Editing accepted ADRs is forbidden.
- Adding `Co-Authored-By` trailers naming LLM assistants is forbidden.

---

## Pre-alpha posture

Mintkey is pre-alpha software. This governance policy reflects that:

- No SLOs.
- No support contracts.
- Breaking changes are possible between any two commits.
- Versioning policy will be documented in `docs/RELEASE.md` (forthcoming, OSS-4).
- No production deployments are supported, endorsed, or documented as safe.
- "Unsupported but possible" is the posture for self-hosted evaluation; see
  [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## License and DCO

Mintkey is licensed under the [Apache License 2.0](LICENSE).

Contributors are encouraged (but not required) to add a `Signed-off-by:` line
to their commits as a DCO (Developer Certificate of Origin) sign-off. This is
standard open-source practice and distinct from the forbidden `Co-Authored-By`
LLM trailer.

```
Signed-off-by: Your Name <your.email@example.com>
```

---

## Future governance

When a second maintainer joins, this document will be updated to define:

- Merge-rights criteria (code review track record, architectural alignment,
  security clearance on the credential broker domain).
- Multi-maintainer decision process (consensus or BDFL-delegate model TBD).
- Release authority (who can tag a release and publish images to GHCR).

Until then, all final decisions rest with the project owner.

---

*Last updated: 2026-05-16. Questions? Open a
[Discussion](https://github.com/WeLikeCode/mintkey/discussions) or email
`the+security@ciprianiacobescu.com`.*
