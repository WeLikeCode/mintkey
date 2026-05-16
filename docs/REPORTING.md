# Reporting: bugs, features, feedback

There are three routes for reporting issues, and they must not be mixed. Using the wrong channel delays triage and, for security issues, creates risk.

- **Security vulnerability** → [`SECURITY.md`](../SECURITY.md). Do not file on GitHub Issues.
- **Reproducible bug or feature request** → GitHub Issues.
- **Architectural ambiguity** → [`docs/architecture/01-architecture/open-questions.md`](architecture/01-architecture/open-questions.md).

If you are debugging an active failure, start at [`docs/DEBUG.md`](DEBUG.md) before filing.

---

## Where things go

| What you have | Where it goes | Label |
|---|---|---|
| Security vulnerability (credential exposure, auth bypass, RCE) | [`SECURITY.md`](../SECURITY.md) — **not Issues** | — |
| Reproducible bug | GitHub Issues | `bug` |
| Feature request | GitHub Issues | `enhancement` |
| Feature that implies an architectural change | GitHub Issues `enhancement` + a proposal in [`docs/architecture/proposal/`](architecture/proposal/) | `enhancement` + `proposal` |
| Architectural ambiguity / open question | Add to [`docs/architecture/01-architecture/open-questions.md`](architecture/01-architecture/open-questions.md) as `OQ-NNN` (per `CLAUDE.md` Principle 2) | — |
| Documentation typo / link rot | Small PR welcome; no Issue needed if fix is < 10 lines | — |
| "I don't understand X" | Discussions; not Issues | — |

> **Security first.** If your bug report touches credential exposure, auth bypass, or any finding covered by the threat model in [`docs/architecture/01-architecture/05-threat-model.md`](architecture/01-architecture/05-threat-model.md), it goes to [`SECURITY.md`](../SECURITY.md) regardless of how it was discovered. The maintainers will reject and delete any security finding filed publicly on Issues.

---

## Bug report template

Copy and fill in the block below. **Do not omit fields** — incomplete reports are triaged last.

````markdown
**Mintkey version**
<!-- Output of: git rev-parse HEAD -->


**Stack state**
<!-- Output of: docker compose ps -->
```
<paste docker compose ps output here>
```

**Symptom**
<!-- One sentence: what did you observe? -->


**Expected behavior**
<!-- Cite the requirement, ADR, or mintkey:code it should have raised.
     e.g. "Per ADR-0006, the broker should return 401 with mintkey:code: token_expired" -->


**Actual behavior**
<!-- Full error response. Must include mintkey:code and mintkey:trace_id if present.
     e.g.:
     {
       "type": "about:blank",
       "title": "Unauthorized",
       "status": 401,
       "mintkey:code": "unauthenticated",
       "mintkey:trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
     }
-->


**Reproduction steps**
<!-- Numbered, copy-pasteable commands against a clean `docker compose up -d` -->
1.
2.
3.

**Logs**
<!-- Relevant slices from docker compose logs. Minimum: the service that returned the error.
     docker compose logs mintkey-<service>-1 --tail 50 -->
```
<paste log slice here>
```

**Trace**
<!-- Jaeger trace ID (from mintkey:trace_id above), if available -->

````

> **Principle:** "report counts and exit codes from the actual test runner" (`CLAUDE.md` Principle 1) applies equally here. A reproduction that can be verified by a maintainer running the exact commands you listed is a good report. A vague description of something you saw once is not.

---

> [!WARNING]
> **Never paste plaintext credentials into an issue body.**
>
> This includes API keys, passwords, tokens, GitHub PATs, the Mintkey KEK, service tokens (`mk_svctoken_*`), or any value that looks like a secret. The maintainers will reject and permanently delete any issue containing plaintext credentials. If your reproduction requires a credential, use a test fixture or redact with `[REDACTED]`. If you believe a real credential has been exposed, file via [`SECURITY.md`](../SECURITY.md) immediately.

---

## Feature request template

````markdown
**What does the agent / operator currently have to do that they shouldn't have to?**
<!-- Describe the friction, not the solution. -->


**Which persona is affected?**
<!-- Reference docs/architecture/00-vision/03-personas-and-stakeholders.md P1-P6 -->


**Quality-attribute scenario this would satisfy**
<!-- If significant, cite or propose a scenario in
     docs/architecture/01-architecture/03-quality-attributes.md (S-*-* format) -->


**Proposed approach (optional)**
<!-- If the change is architectural, a proposal under docs/architecture/proposal/ is required.
     See docs/architecture/proposal/README.md for format. -->

````

Features that imply a new wire surface, a new auth scheme, or a new audit event type require a proposal. See [`CONTRIBUTING.md`](../CONTRIBUTING.md) §7 for the proposal process.

---

## What makes a good issue

- **Reproducible against a clean `docker compose up -d`.** If it only happens in a specific local state, narrow the reproduction before filing.
- **Captures `mintkey:code` and `mintkey:trace_id`.** These are the fastest path to the offending code path. Both are present in every RFC 7807 error body produced by the system (see [`openapi.yaml`](architecture/contracts/rest/openapi.yaml) error schema definition).
- **Cites the ADR, contract, or requirement the actual behavior violates.** "This is wrong" is not a citation. "Per `ADR-0006`, tokens must expire in ≤ 60 s; this token is valid for 3600 s" is.
- **Does not contain plaintext credentials** (see the warning box above — the maintainers will reject and delete such issues).
- **Includes `git rev-parse HEAD`** so the maintainer can reproduce against the exact commit.

---

## What we do with reports

- **Triage target:** 7 days.
- We label the issue, link it to the offending ADR / requirement / contract, and either fix on `main` or convert to a proposal.
- Architectural ambiguities become `OQ-NNN` entries in [`docs/architecture/01-architecture/open-questions.md`](architecture/01-architecture/open-questions.md) and get phase-assigned.
- Bugs that reveal a `mintkey:code` value not present in the `x-mintkey-error-codes` block of [`openapi.yaml`](architecture/contracts/rest/openapi.yaml) are treated as contract violations; the fix must update both the code and the spec together.

---

## Feedback that is not a bug

We read it. We do not promise to act on it. We do not commit to a roadmap beyond [`docs/architecture/00-vision/06-roadmap.md`](architecture/00-vision/06-roadmap.md). If the feedback implies a design change, follow the proposal process in [`CONTRIBUTING.md`](../CONTRIBUTING.md) §7.
