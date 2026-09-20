/**
 * Unit tests for the Requests_Review_Area action guards + body builder (Task 8.4).
 *
 * These are the React-free pure guards from Task 8.3 that carry the client-side
 * behavior for the Reject and Finalize controls:
 *   - rejectReasonValid  (Req 8.5 — block submission on empty/whitespace reason)
 *   - requiredSecretFieldNames + finalizeEnabled
 *                        (Req 6.8 — Finalize enabled only once every required
 *                         operator secret field holds a non-empty value)
 *   - buildProposalActionBody
 *                        (Req 6.1/6.2 — never echoes an un-typed secret; operator
 *                         config edits override agent-proposed values)
 *
 * ADD-ONLY: new file; no existing test or source module is modified.
 *
 * Requirements: 6.8, 8.5 (with 6.1, 6.2 coverage on the body builder).
 */

import { describe, it, expect } from "vitest";
import {
  rejectReasonValid,
  requiredSecretFieldNames,
  finalizeEnabled,
  buildProposalActionBody,
  type AccessRequest,
} from "../src/components/pages/access-requests.utils.js";

function makeRequest(overrides: Partial<AccessRequest> = {}): AccessRequest {
  return {
    request_id: "request_01ACCESS00000000000000001",
    kind: "access",
    status: "pending",
    requesting_agent_id: "agent_01AAAAAAAAAAAAAAAAAAAAAAA1",
    service_id: "svc_01SERVICE0000000000000001",
    action: "read",
    target_agent_id: null,
    share_direction: null,
    proposed_config: null,
    reason: null,
    created_at: "2026-06-01T00:00:00Z",
    expires_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

/** An integration proposal whose auth_scheme has a single required secret field. */
function makeApiKeyIntegration(): AccessRequest {
  return makeRequest({
    request_id: "request_01INT00000000000000000001",
    kind: "integration",
    service_id: null,
    action: null,
    proposed_config: {
      name: "Stripe API",
      auth_scheme: "api_key_header",
      header_name: "X-API-Key",
    },
  });
}

describe("rejectReasonValid (Req 8.5)", () => {
  it("blocks an empty reason", () => {
    expect(rejectReasonValid("")).toBe(false);
  });

  it("blocks a spaces-only reason", () => {
    expect(rejectReasonValid("   ")).toBe(false);
  });

  it("blocks a tab/newline-only reason", () => {
    expect(rejectReasonValid("\t\n")).toBe(false);
  });

  it("allows a non-empty reason", () => {
    expect(rejectReasonValid("duplicate of an existing grant")).toBe(true);
  });

  it("allows a reason with surrounding whitespace as long as it has content", () => {
    expect(rejectReasonValid("  no  ")).toBe(true);
  });
});

describe("requiredSecretFieldNames (Req 6.8)", () => {
  it("api_key_header → ['value'] (the only required secret field)", () => {
    expect(requiredSecretFieldNames(makeApiKeyIntegration())).toEqual(["value"]);
  });

  it("basic_auth → ['password'] (username is non-secret)", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { auth_scheme: "basic_auth" },
    });
    expect(requiredSecretFieldNames(r)).toEqual(["password"]);
  });

  it("oauth2_client_credentials → ['client_secret'] (ids/urls are non-secret)", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { auth_scheme: "oauth2_client_credentials" },
    });
    expect(requiredSecretFieldNames(r)).toEqual(["client_secret"]);
  });

  it("returns [] for a non-integration request", () => {
    expect(requiredSecretFieldNames(makeRequest({ kind: "access" }))).toEqual([]);
  });

  it("returns [] when the auth_scheme is missing or unknown", () => {
    const unknown = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { auth_scheme: "made_up_scheme" },
    });
    expect(requiredSecretFieldNames(unknown)).toEqual([]);
  });
});

describe("finalizeEnabled (Req 6.8)", () => {
  it("disabled when the required secret is absent from secretValues", () => {
    expect(finalizeEnabled(makeApiKeyIntegration(), {})).toBe(false);
  });

  it("disabled when the required secret is empty", () => {
    expect(finalizeEnabled(makeApiKeyIntegration(), { value: "" })).toBe(false);
  });

  it("disabled when the required secret is whitespace-only", () => {
    expect(finalizeEnabled(makeApiKeyIntegration(), { value: "   " })).toBe(false);
    expect(finalizeEnabled(makeApiKeyIntegration(), { value: "\t\n" })).toBe(false);
  });

  it("enabled once the required secret is filled with a non-empty value", () => {
    expect(finalizeEnabled(makeApiKeyIntegration(), { value: "sk_live_123" })).toBe(
      true,
    );
  });

  it("requires ALL required secret fields when a scheme has more than one", () => {
    // mtls → client_key_pem is the only required secret; keep it single but
    // assert the every() semantics with an extra irrelevant filled key.
    const r = makeApiKeyIntegration();
    expect(finalizeEnabled(r, { header_name: "X-API-Key" })).toBe(false);
    expect(finalizeEnabled(r, { header_name: "X-API-Key", value: "k" })).toBe(true);
  });

  it("disabled for a non-integration request (no Finalize path)", () => {
    expect(finalizeEnabled(makeRequest({ kind: "access" }), {})).toBe(false);
  });

  it("disabled for an integration whose scheme has no secret fields", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { auth_scheme: "none" },
    });
    expect(finalizeEnabled(r, {})).toBe(false);
  });
});

describe("buildProposalActionBody (Req 6.1, 6.2)", () => {
  it("omits an un-typed secret and carries the auth_scheme in the credential body", () => {
    const r = makeApiKeyIntegration();
    const body = buildProposalActionBody(r, {}, {});
    expect(body.credential["auth_scheme"]).toBe("api_key_header");
    // Never echoes a prefilled/blank secret when none was typed (Req 6.1).
    expect("value" in body.credential).toBe(false);
  });

  it("includes only non-empty typed secrets in the credential body", () => {
    const r = makeApiKeyIntegration();
    const body = buildProposalActionBody(r, { value: "sk_live_123" }, {});
    expect(body.credential["value"]).toBe("sk_live_123");
  });

  it("applies operator config edits over the agent-proposed values (Req 6.2)", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: {
        name: "Stripe",
        base_url: "https://api.stripe.com",
        auth_scheme: "api_key_header",
      },
    });
    const body = buildProposalActionBody(r, {}, { base_url: "https://edited.example.com" });
    // Operator edit wins over the proposed value.
    expect(body.config["base_url"]).toBe("https://edited.example.com");
    // Un-edited proposed non-secret config is preserved.
    expect(body.config["name"]).toBe("Stripe");
  });
});
