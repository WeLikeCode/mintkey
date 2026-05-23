# OSS Readiness — Open Escalations

**Session:** 2026-05-16-oss-readiness
**Status:** All 7 items RESOLVED 2026-05-16. Chunk dispatch is no longer blocked.

| # | Decision | Resolved |
|---|---|---|
| E-1 | Apache-2.0 confirmed | 2026-05-16 |
| E-2 | `https://github.com/WeLikeCode/mintkey` (clone URL: `https://github.com/WeLikeCode/mintkey.git`) | 2026-05-16 |
| E-3 | `the+security@ciprianiacobescu.com` | 2026-05-16 |
| E-4 | GHCR (`ghcr.io/welikecode/mintkey-*`) — applied as default | 2026-05-16 |
| E-5 | Defer release workflow entirely; document path in `docs/RELEASE.md` only | 2026-05-16 |
| E-6 | "Unsupported but possible" with explicit caveats | 2026-05-16 |
| E-7 | GitHub Discussions enabled — applied as default | 2026-05-16 |

Per-item details + original recommendations preserved below for the closing report.

---

## E-1 — Apache-2.0 license intent

**Question:** Is Apache-2.0 the intended license for the OSS push? `README.md` claims Apache-2.0 (line 17 of the status table) but no `LICENSE` file exists in the repo.

**Why it matters:** OSS-1 cannot add the root `LICENSE` text without this confirmation. An MIT or BSL-1.1 choice would change the file content entirely; a copyleft license (AGPL) would change the entire contribution story. Chunk OSS-1 is fully blocked on this.

**Evidence:** `README.md:17` — `| License | Apache-2.0 (see root \`LICENSE\`) |`; `find . -maxdepth 2 -iname 'license*'` → no output.

**Recommendation:** Apache-2.0. It matches the existing README claim, is the standard for cloud-native credential-broker tooling (Vault, Cert-Manager, Crossplane are all Apache-2.0), and allows downstream commercial embedding without copyleft constraints. Add the verbatim text from https://www.apache.org/licenses/LICENSE-2.0.txt as `LICENSE` at repo root. No `NOTICE` file is required unless third-party Apache-2.0 components with attribution requirements are vendored.

**Status:** RESOLVED (see top table)

---

## E-2 — Final GitHub repository URL

**Question:** What is the public GitHub repository URL for Mintkey? The value is needed wherever `<repo-url>` appears.

**Why it matters:** Found in 4 places: `README.md:78`, `QUICKSTART.md:24`, `marketing/index.html:242`, and implicitly in `SECURITY.md` (which references the maintainer contact that will include a link). Chunk OSS-1 replaces these placeholders. OSS-7 (marketing) also needs it for the CTA buttons. The OpenAPI `info.contact.url` (currently `https://example.invalid/mintkey`) will be set to this URL. Cannot proceed without it.

**Evidence:** `README.md:78` — `git clone <repo-url> mintkey`; `QUICKSTART.md:24` — `git clone <repo-url> mintkey && cd mintkey`; `marketing/index.html:242` — `git clone <repo-url>`; `openapi.yaml:71` — `url: https://example.invalid/mintkey`.

**Recommendation:** Confirm the GitHub org and repo name before dispatch (e.g., `https://github.com/<org>/mintkey`). Once confirmed, OSS-1 can do a single targeted substitution across all four locations.

**Status:** RESOLVED (see top table)

---

## E-3 — Final maintainer and security contact email

**Question:** What email address should replace `<TBD-by-architect>` in `SECURITY.md` and `maintainers@example.invalid` in `openapi.yaml`?

**Why it matters:** `SECURITY.md:21` is the primary channel for vulnerability reporters. A `maintainers@example.invalid` in the public OpenAPI spec is embarrassing and immediately signals an unprepared project. Chunk OSS-1 depends on this. The security email is also the expected value for a forthcoming `SECURITY.md` `security-txt` link. Cannot ship to OSS without a real email.

**Evidence:** `SECURITY.md:21` — `Email: <TBD-by-architect>`; `openapi.yaml:72` — `email: maintainers@example.invalid`.

**Recommendation:** Use a dedicated security alias (e.g., `security@<domain>`) rather than a personal address. GitHub's private vulnerability reporting can be the backup, but a public email is the expected minimum for OSS projects. If the domain is not yet set up, use the personal maintainer address temporarily and note it is interim.

**Status:** RESOLVED (see top table)

---

## E-4 — Whether GHCR is the intended image registry

**Question:** Should the release workflow publish container images to GitHub Container Registry (`ghcr.io`) or to another registry (Docker Hub, Quay.io, etc.)?

**Why it matters:** Chunk OSS-4 (release pipeline) and OSS-3 (CI gates) need to know where to push images, which OIDC trust configuration to add, and what `docker/build-push-action` target to use. The SBOM/provenance attestation strategy also varies by registry. Getting this wrong means the release workflow is built for the wrong target and has to be rewritten.

**Recommendation:** GHCR (`ghcr.io/<org>/mintkey-*`). It is free for public repos, natively integrated with GitHub Actions OIDC (no stored Docker Hub credentials needed), and supports OCI artifact attachments for SBOM/SLSA provenance. Standard for projects hosted on GitHub.

**Status:** RESOLVED (see top table)

---

## E-5 — Release automation: publish images immediately or dry-run only

**Question:** On the first public technical-preview release, should the release workflow push images to the registry immediately (triggered by a version tag), or should it only dry-run (`--push=false`) until the owner manually promotes?

**Why it matters:** Chunk OSS-4 implements the release workflow. A "push immediately on tag" model is simpler but irreversible — once `v0.1.0-preview.1` is on GHCR it is public. A dry-run-first model adds a manual approval gate (GitHub Environment approval). The wrong default could result in unintended public image publication before the codebase is ready.

**Recommendation:** Dry-run by default (`--push=false`), with a separate protected Environment (`release`) that the owner must approve before images go live. This is one extra workflow job and one GitHub Environment config. Gives a safety net for the first release while keeping the automation in place.

**Status:** RESOLVED (see top table)

---

## E-6 — Production deployment docs scope

**Question:** Should the deployment documentation (`docs/architecture/05-deployment/README.md` and any new `docs/DEPLOYMENT.md` or `docs/PRODUCTION-READINESS.md`) explicitly call production use "out of scope / unsupported for pre-alpha" — or should it describe a production path as "possible but unsupported"?

**Why it matters:** `docs/architecture/05-deployment/README.md` is currently an architecture sketch ("Coming in iteration 2"). Chunk OSS-5 will add hardened container packaging; chunk OSS-6 will add how-to-use docs. The boundary between "here's how to self-host for evaluation" and "here's how to run this in production" needs an explicit owner decision, because any production guidance implies support commitment and may create liability expectations in OSS consumers.

**Recommendation:** "Unsupported but possible" with a prominent warning. Document the Docker Compose self-host path as the supported evaluation path, describe the gap to production (no HA, no managed secrets, no ingress TLS docs, no backup/restore), and explicitly state that production hardening is out of scope for the pre-alpha. This is honest, protects the project from support burden, and is consistent with the existing `x-mintkey-stability: experimental` API stance.

**Status:** RESOLVED (see top table)

---

## E-7 — Public GitHub Discussions

**Question:** Should the repository have GitHub Discussions enabled as the public community forum?

**Why it matters:** Chunk OSS-2 adds `SUPPORT.md`. The content of `SUPPORT.md` depends on where users are directed for help — Discussions, a Slack/Discord, a mailing list, or "GitHub Issues only." Governance files (`GOVERNANCE.md`) also reference the community forum model. Enabling Discussions is a one-click org setting, but once public contributions start flowing it creates an ongoing moderation commitment.

**Recommendation:** Yes, enable GitHub Discussions with at minimum a "Q&A" and "Ideas" category. Direct `SUPPORT.md` there. This is lower overhead than Slack/Discord for a pre-alpha, keeps discussion searchable and linked to code, and GitHub provides spam filtering. Defer a dedicated Slack/Discord until the project has a community large enough to warrant it.

**Status:** RESOLVED (see top table)
