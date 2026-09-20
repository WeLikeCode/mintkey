/**
 * Seed helper for the Requests_Review_Area e2e (task 10.1).
 *
 * There is NO operator REST endpoint that creates an access request — the five
 * operator endpoints are list / get / approve / reject / test. Access requests
 * are created by AGENTS via the MCP tool `request_access`
 * (POST {MCP}/v1/tools/request_access, authenticated by a Bearer Agent API Key;
 * tenant resolved from that key's auth context, ADR-0009).
 *
 * So the realistic seed — consistent with the existing fixtures that reach
 * DB/API state through the real services — is:
 *
 *   1. create a Service     (existing fixture `createTestService`, admin-api)
 *   2. create an Agent       (existing fixture `createTestAgent`, admin-api;
 *                             returns the plaintext Agent API Key once)
 *   3. call the MCP tool     `request_access({ service_id, action })` with
 *                            `Authorization: Bearer mk_agent_<key>`
 *      → returns { request_id, status: "pending" }
 *
 * This exercises the same create path a real agent would, and yields a pending
 * `access_requests` row the operator can then Approve / Reject in the UI.
 *
 * NEW file — adds only new exports; touches no existing fixture.
 *
 * Source: agent-access-requests spec Task 10.1; Req 15.4; ADR-0009;
 *         apps/mcp-server/src/mcp_server/tools/request_access.py.
 */

import { createTestAgent, createTestService } from "./test-data.js";

/** MCP server base URL — host-mapped 8082 in infra/compose (see docker-compose.yml). */
const MCP_URL = process.env.MINTKEY_MCP_URL ?? process.env.MCP_URL ?? "http://localhost:8082";

export interface SeededAccessRequest {
  /** The `request_` prefixed-ULID wire id the operator UI renders. */
  requestId: string;
  /** The requesting agent's wire id. */
  agentId: string;
  /** The service the grant is requested on. */
  serviceId: string;
  /** The requested action. */
  action: string;
}

/**
 * Seed one pending `kind=access` request for the given tenant.
 *
 * @param opts.tenantId  tenant to seed under (PLAYWRIGHT_TENANT_ID).
 * @param opts.label     unique-ish label to disambiguate the created service/agent.
 * @param opts.action    requested action (defaults to a unique read action so
 *                        repeated runs never collide with an existing grant or a
 *                        duplicate-pending guard — Req 1.5 / 1.6).
 * @param token          optional PLAYWRIGHT_API_JWT (forwarded to the fixtures).
 */
export async function seedPendingAccessRequest(
  opts: { tenantId: string; label: string; action?: string },
  token?: string,
): Promise<SeededAccessRequest> {
  const unique = `${opts.label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const action = opts.action ?? `read:${unique}`.slice(0, 60);

  const serviceId = await createTestService(
    { tenantId: opts.tenantId, name: `ReqSvc ${unique}`, slug: `req-svc-${unique}` },
    token,
  );
  const { agentId, apiKey } = await createTestAgent(
    { tenantId: opts.tenantId, name: `ReqAgent ${unique}` },
    token,
  );

  if (!apiKey) {
    throw new Error(
      "seedPendingAccessRequest: agent creation did not return an Agent API Key — " +
        "cannot authenticate the MCP request_access call.",
    );
  }

  const resp = await fetch(`${MCP_URL}/v1/tools/request_access`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ service_id: serviceId, action }),
  });

  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new Error(
      `seedPendingAccessRequest: MCP request_access failed (${resp.status}): ${detail}`,
    );
  }

  const data = (await resp.json()) as { request_id?: string; status?: string };
  if (!data.request_id || data.status !== "pending") {
    throw new Error(
      `seedPendingAccessRequest: unexpected MCP response: ${JSON.stringify(data)}`,
    );
  }

  return { requestId: data.request_id, agentId, serviceId, action };
}
