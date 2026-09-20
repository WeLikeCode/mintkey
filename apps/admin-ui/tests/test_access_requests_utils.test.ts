/**
 * Unit tests for the Requests_Review_Area pure utilities (Task 8.2).
 *
 * Covers filterRequests, targetSummary, operatorSecretFields (Req 4.6 — derives
 * the EMPTY operator-supplied secret fields from the proposed auth_scheme),
 * and nonSecretConfigEntries (defensive secret-denylist omission).
 *
 * Requirements: 4.1, 4.2, 4.6.
 */

import { describe, it, expect } from "vitest";
import {
  filterRequests,
  targetSummary,
  operatorSecretFields,
  nonSecretConfigEntries,
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

describe("filterRequests", () => {
  const access = makeRequest({ kind: "access", status: "pending" });
  const share = makeRequest({
    request_id: "request_01SHARE000000000000000001",
    kind: "share",
    status: "approved",
  });
  const integration = makeRequest({
    request_id: "request_01INT00000000000000000001",
    kind: "integration",
    status: "rejected",
  });
  const all = [access, share, integration];

  it("returns all when no filters set", () => {
    expect(filterRequests(all, { status: "", kind: "" })).toHaveLength(3);
  });

  it("filters by kind", () => {
    const out = filterRequests(all, { status: "", kind: "share" });
    expect(out).toHaveLength(1);
    expect(out[0].kind).toBe("share");
  });

  it("filters by status", () => {
    const out = filterRequests(all, { status: "pending", kind: "" });
    expect(out).toHaveLength(1);
    expect(out[0].status).toBe("pending");
  });

  it("applies status AND kind together", () => {
    expect(
      filterRequests(all, { status: "approved", kind: "access" }),
    ).toHaveLength(0);
    expect(
      filterRequests(all, { status: "approved", kind: "share" }),
    ).toHaveLength(1);
  });
});

describe("targetSummary", () => {
  it("access → 'service · action'", () => {
    const r = makeRequest({ kind: "access", service_id: "svc_x", action: "read" });
    expect(targetSummary(r)).toBe("svc_x · read");
  });

  it("share → 'service · action → target (direction)'", () => {
    const r = makeRequest({
      kind: "share",
      service_id: "svc_x",
      action: "write",
      target_agent_id: "agent_y",
      share_direction: "outbound",
    });
    expect(targetSummary(r)).toBe("svc_x · write → agent_y (outbound)");
  });

  it("integration → proposed config name", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { name: "Stripe API", auth_scheme: "api_key_header" },
    });
    expect(targetSummary(r)).toBe("Stripe API");
  });

  it("integration without a name → placeholder", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { auth_scheme: "api_key_header" },
    });
    expect(targetSummary(r)).toBe("(integration proposal)");
  });
});

describe("operatorSecretFields", () => {
  it("returns only secret fields for the proposed auth_scheme (api_key_header → value)", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { auth_scheme: "api_key_header", header_name: "X-API-Key" },
    });
    const fields = operatorSecretFields(r);
    expect(fields.map((f) => f.name)).toEqual(["value"]);
    expect(fields.every((f) => f.secret)).toBe(true);
  });

  it("basic_auth → password only (username is non-secret)", () => {
    const r = makeRequest({
      kind: "integration",
      service_id: null,
      action: null,
      proposed_config: { auth_scheme: "basic_auth" },
    });
    expect(operatorSecretFields(r).map((f) => f.name)).toEqual(["password"]);
  });

  it("returns [] for non-integration requests", () => {
    expect(operatorSecretFields(makeRequest({ kind: "access" }))).toEqual([]);
  });

  it("returns [] when auth_scheme is missing or unknown", () => {
    const missing = makeRequest({
      kind: "integration",
      proposed_config: { name: "x" },
    });
    expect(operatorSecretFields(missing)).toEqual([]);
    const unknown = makeRequest({
      kind: "integration",
      proposed_config: { auth_scheme: "made_up_scheme" },
    });
    expect(operatorSecretFields(unknown)).toEqual([]);
  });
});

describe("nonSecretConfigEntries", () => {
  it("returns non-secret entries as [key, displayValue] pairs", () => {
    const r = makeRequest({
      kind: "integration",
      proposed_config: {
        name: "Stripe",
        base_url: "https://api.stripe.com",
        actions: ["read", "write"],
      },
    });
    const entries = nonSecretConfigEntries(r);
    const map = Object.fromEntries(entries);
    expect(map["name"]).toBe("Stripe");
    expect(map["base_url"]).toBe("https://api.stripe.com");
    expect(map["actions"]).toBe(JSON.stringify(["read", "write"]));
  });

  it("defensively omits any denylisted secret-looking keys", () => {
    const r = makeRequest({
      kind: "integration",
      proposed_config: {
        client_id: "abc",
        client_secret: "SHOULD_NOT_RENDER",
        password: "SHOULD_NOT_RENDER",
        api_key: "SHOULD_NOT_RENDER",
        private_key: "SHOULD_NOT_RENDER",
        token: "SHOULD_NOT_RENDER",
      },
    });
    const keys = nonSecretConfigEntries(r).map(([k]) => k);
    expect(keys).toContain("client_id");
    expect(keys).not.toContain("client_secret");
    expect(keys).not.toContain("password");
    expect(keys).not.toContain("api_key");
    expect(keys).not.toContain("private_key");
    expect(keys).not.toContain("token");
  });

  it("returns [] when there is no proposed_config", () => {
    expect(nonSecretConfigEntries(makeRequest({ proposed_config: null }))).toEqual(
      [],
    );
  });
});
