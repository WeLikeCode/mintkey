# ADR‑0028: Python 3.14 for dev-only Docker images (mock-backend, seed-job)

## Status
Accepted — 2026-06-27. Amends [ADR‑0012](0012-python-stack-pin.md) §"Python version".

## Context
Two Mintkey **dev/test-only** container images carry a Python base image:

- **`apps/mock-backend/`** — a FastAPI stub backend used by the docker-compose
  dev environment and the e2e smoke test. Not a production service; never
  deployed.
- **`apps/seed-job/`** — a one-shot init container that writes bootstrap secrets
  into the `bootstrap_secrets` named volume at compose startup. Not a production
  service; exits immediately after seeding.

On 2026-06-27, Dependabot PRs **#221** and **#222** merged, bumping the base
image of both Dockerfiles from `python:3.12-slim-bookworm` to
`python:3.14-slim-bookworm` (digest-pinned). Python 3.14 is stable (released
October 2025).

[ADR‑0012](0012-python-stack-pin.md) §"Python version" pins **Python 3.12+** for
the Python stack. That ADR was written for the two *production* Python services —
the **Admin REST API (C2)** and the **MCP Server (C4)** — which share the
`mintkey-models` package, SQLAlchemy 2.x async layer, OIDC client, and OTel
instrumentation. The pin's intent is to keep those two services on a single,
jointly-validated interpreter so upgrades are coordinated.

The mock-backend and seed-job images share none of that machinery. mock-backend
is a thin FastAPI stub; seed-job is a small `pip install` + `python main.py`
one-shot. Neither imports `mintkey-models`, the SQLAlchemy mirror, or the OTel
SDK in a way that couples them to the production interpreter pin. The question is
whether ADR‑0012's 3.12 pin should be read as binding on these dev images, or
whether they are free to track the latest stable Python.

## Decision
**Accept Python 3.14 for the dev-only images** (`apps/mock-backend/` and
`apps/seed-job/`). These images may track the latest stable Python release.

**The Admin REST API and MCP Server remain on Python 3.12** per
[ADR‑0012](0012-python-stack-pin.md). This ADR does **not** move the production
services; that would require a separate decision validating the shared
`mintkey-models` / SQLAlchemy / OTel stack against 3.14.

Rationale:

- **3.14 is stable** — released October 2025, with no breaking changes that
  affect either of these simple dev images. mock-backend is a FastAPI stub;
  seed-job is a `pip install` + file-writing one-shot. Both ran green on 3.14 in
  the PR #221 / #222 CI.
- **Per-service pin, not repo-wide** — ADR‑0012's intent is to keep the two
  *production* Python services coordinated on one interpreter, not to freeze
  every Python container in the repo. Reading the pin as repo-wide would force
  Dependabot churn to be rejected for no production benefit.
- **Lower risk surface** — neither image is deployed, network-exposed long-lived,
  or part of the credential path. The blast radius of an interpreter bump is the
  dev/compose and CI environments only.

### ADR‑0012 amendment
[ADR‑0012](0012-python-stack-pin.md) §"Python version" (**Python 3.12+**) applies
to the **Admin REST API (C2)** and the **MCP Server (C4)** only. Dev/test-only
images (`apps/mock-backend/`, `apps/seed-job/`) are **not** bound by that pin and
may track the latest stable Python release (currently 3.14).

## Consequences

### Positive
- Dependabot will continue to deliver Python base-image updates (3.14.x and
  later stable lines) for mock-backend and seed-job automatically, without each
  bump being mis-flagged as an ADR‑0012 violation.
- The intent of ADR‑0012 is made explicit: the 3.12 pin is a *per-production-
  service* coordination guarantee, not a repo-wide freeze.
- Dev images stay on a supported, patched interpreter with current security
  fixes.

### Costs
- Two interpreter lines now exist in the repo (3.12 for production services,
  3.14 for the two dev images). Anyone reasoning about "the Python version" must
  consult the per-service distinction this ADR records.

### Risks
- A future Python release could introduce a breaking change that affects
  mock-backend or seed-job. Mitigation: both images run in CI (e2e smoke /
  compose startup), so a breaking bump fails the build before merge; base images
  remain digest-pinned and re-pinned quarterly.

## Related
- [ADR‑0012 Python stack pin](0012-python-stack-pin.md) — amended here; the 3.12 pin
  now reads as production-services-only.
- [ADR‑0005 admin tech stack](0005-admin-tech-stack.md) — Admin REST API Python stack.
- [ADR‑0009 MCP server stack](0009-mcp-server-stack-python.md) — MCP Server Python stack.
