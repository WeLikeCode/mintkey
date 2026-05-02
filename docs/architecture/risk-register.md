# Risk Register

**Owner:** Alexandru Iacobescu (architect of record)
**Last updated:** 2026-05-10
**Seeded by:** project-setup wizard (Q25 answers + threat model)

Entries follow the three-question test (`rule-real-risks-not-padding.md`):
1. What specifically breaks?
2. What evidence shows it's real?
3. Which decision or component depends on this?

---

## Active risks

### R-001 — Egress Proxy compromise exposes plaintext credentials

**What breaks:** An attacker who gains code execution inside the proxy plugin process can read plaintext credentials from process memory during the request mutation step. Every credential for every service routed through that proxy instance is at risk for the duration of the compromise.

**Evidence:** `docs/architecture/01-architecture/05-threat-model.md` §Top architectural risks #1 explicitly names this as the highest-severity risk. The proxy is the only component where the real credential exists in plaintext (by design — it must inject it). This is an architectural necessity, not a coding flaw.

**Affected component:** Egress Proxy plugin (D1, `services/proxy-plugin/`).

**Mitigations in place:**
- Small attack surface: single binary, hardened distroless image, minimal dependencies.
- No plugin loading at runtime; no dynamic code execution.
- Mandatory code review for all proxy plugin changes.
- Optional namespaced/seccomp container.
- Plaintext zeroed after each request scope (ADR-0014).

**Status:** Open — mitigations reduce likelihood; residual risk is accepted as architectural necessity.

---

### R-002 — JWT signing key compromise enables arbitrary token minting

**What breaks:** An attacker who exfiltrates the Credential Broker's Ed25519 private signing key can mint valid JWTs for any agent, any service, and any tenant — bypassing all permission checks. The Egress Proxy trusts the JWT signature; a valid signature is sufficient for credential injection.

**Evidence:** `docs/architecture/01-architecture/05-threat-model.md` §Top architectural risks #2. The broker holds the private key in process memory (ADR-0006). JWKS-based public key distribution means the proxy cannot detect a forged token if the signature is valid.

**Affected component:** Credential Broker (C5, `services/broker/`).

**Mitigations in place:**
- Key lives in a dedicated process with narrow attack surface.
- Periodic rotation supported; JWKS `kid`-based key versioning (ADR-0006).
- Optional HSM backing (Phase 2).
- `jti` denylist in Postgres limits replay window even with a valid key (ADR-0016).

**Status:** Open — HSM backing deferred to Phase 2; residual risk accepted for MVP.

---

### R-003 — Audit coverage gap allows undetected state mutation

**What breaks:** A code path that mutates state (credential write, permission grant, token issuance) without calling `audit.emit()` creates a silent gap in the audit log. An operator investigating "what did agent X do" gets an incomplete picture; a compliance audit fails; a forensic investigation misses the event.

**Evidence:** `docs/architecture/01-architecture/05-threat-model.md` §Top architectural risks #4. The audit chokepoint is currently enforced by convention, not by a CI architecture test. ADR-0014 mandates the hash chain and the chokepoint but the enforcement test is listed as `⏳` in `docs/architecture/00-vision/07-kiro-readiness.md` §Quality gates.

**Affected component:** Audit Service (C7) and every state-change handler across Admin REST API, MCP Server, Credential Broker, and Vault Adapter.

**Mitigations in place:**
- Single `audit.emit()` helper in both Go (`internal/audit`) and Python (`admin_api/audit`) — one call site per language.
- Append-only table with mandatory per-tenant hash chain (ADR-0014).
- DB triggers as defense-in-depth for AdminJS direct writes (ADR-0005).

**Mitigation gap:** Architecture test asserting 100% state-change handler coverage is not yet written (OQ-002 adjacent). This is the primary residual risk.

**Status:** Open — architecture test must be written before Phase 1 exit (milestone 1.0 acceptance criterion).

---

## Resolved risks

*(None yet — register seeded at project setup.)*

---

## Maintenance

- New risks from adversarial reviews land here as `R-NNN` after passing the three-question test.
- Use the `risk-register-update` skill to add, validate, or invalidate entries.
- Risks that fail the three-question test are rejected — see `rule-real-risks-not-padding.md`.
- When a risk is fully mitigated, move to Resolved with the ADR or commit reference.
