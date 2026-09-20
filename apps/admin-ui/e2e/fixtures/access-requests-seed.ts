/**
 * Seed helper for the Requests_Review_Area e2e (task 10.1).
 *
 * There is NO operator REST endpoint that creates an access request — the five
 * operator endpoints are list / get / approve / reject / test. Access requests
 * are created by AGENTS via the MCP tool `request_access`
 * (POST {MCP}/v1/tools/request_access, authenticated by a Bearer Agent API Key;
 * tenant resolved from that key's auth context, ADR-0009).
 *
 * So the realistic seed — consistent with the way a real operator + agent reach
 * this state — is:
 *
 *   1. create a Service  (admin-api POST /v1/tenants/{tid}/services)
 *   2. create an Agent   (admin-api POST /v1/tenants/{tid}/agents — returns the
 *                         plaintext Agent API Key once, on the Agent schema's
 *                         `api_key` field)
 *   3. call the MCP tool `request_access({ service_id, action })` with
 *      `Authorization: Bearer mk_agent_<key>` → { request_id, status:"pending" }
 *
 * AUTH NOTE (why this uses the browser's session, not internal-login):
 * this deployment is SSO-only (ADR-0020) — `POST /v1/auth/internal-login`
 * returns 404 (`not_found`) because `operators.internal_password_hash IS NULL`.
 * The admin-api writes therefore CANNOT use a password login. Instead the seed
 * reuses the operator's already-authenticated browser session: the caller
 * passes Playwright's `page.request` (an APIRequestContext that shares the
 * page's cookies — the real `mintkey_session` + `csrf_token` set by the
 * Keycloak OIDC flow in global-setup). We attach the CSRF double-submit header
 * from the `csrf_token` cookie so admin-api's CSRF middleware accepts the write.
 *
 * NEW file — adds only new exports; touches no existing fixture.
 *
 * Source: agent-access-requests spec Task 10.1; Req 15.4; ADR-0009, ADR-0020;
 *         apps/mcp-server/src/mcp_server/tools/request_access.py.
 */

import type { APIRequestContext } from "@playwright/test";

/** MCP server base URL — host-mapped 8082 primary / 8182 test-ns. */
const MCP_URL = process.env.MINTKEY_MCP_URL ?? process.env.MCP_URL ?? "http://localhost:8082";
/** admin-api base URL — host-mapped 8080 primary / 8180 test-ns. */
const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";

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

/** Read a cookie value from the authenticated request context's storage state. */
async function csrfTokenFrom(request: APIRequestContext): Promise<string> {
  const state = await request.storageState();
  const csrf = state.cookies.find((c) => c.name === "csrf_token");
  if (!csrf) {
    throw new Error(
      "seedPendingAccessRequest: no csrf_token cookie on the authenticated " +
        "request context — the operator SSO session did not initialise " +
        "(check global-setup / PLAYWRIGHT_PASS).",
    );
  }
  return csrf.value;
}

/**
 * Seed one pending `kind=access` request for the given tenant.
 *
 * @param opts.request   Playwright `page.request` — an APIRequestContext that
 *                       shares the authenticated browser cookies (SSO session).
 * @param opts.tenantId  tenant to seed under (PLAYWRIGHT_TENANT_ID).
 * @param opts.label     unique-ish label to disambiguate the created service/agent.
 * @param opts.action    requested action (defaults to a unique read action so
 *                        repeated runs never collide with an existing grant or a
 *                        duplicate-pending guard — Req 1.5 / 1.6).
 */
export async function seedPendingAccessRequest(opts: {
  request: APIRequestContext;
  tenantId: string;
  label: string;
  action?: string;
}): Promise<SeededAccessRequest> {
  const { request, tenantId } = opts;
  const unique = `${opts.label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const action = opts.action ?? `read:${unique}`.slice(0, 60);
  const csrf = await csrfTokenFrom(request);
  const writeHeaders = { "Content-Type": "application/json", "X-Mintkey-Csrf": csrf };

  // 1. Service (admin-api, authenticated via shared SSO cookies + CSRF).
  const svcResp = await request.post(`${ADMIN_API}/v1/tenants/${tenantId}/services`, {
    headers: writeHeaders,
    data: {
      name: `ReqSvc ${unique}`,
      slug: `req-svc-${unique}`.slice(0, 60),
      base_url: "https://example.com",
      auth_scheme: "api_key_header",
    },
  });
  if (!svcResp.ok()) {
    throw new Error(
      `seedPendingAccessRequest: create service failed (${svcResp.status()}): ${await svcResp.text()}`,
    );
  }
  const svc = (await svcResp.json()) as { id?: string; service_id?: string };
  const serviceId = svc.id ?? svc.service_id ?? "";

  // 2. Agent — the plaintext Agent API Key is returned once on `api_key`.
  const agentResp = await request.post(`${ADMIN_API}/v1/tenants/${tenantId}/agents`, {
    headers: writeHeaders,
    data: { name: `ReqAgent ${unique}`, description: "e2e seed" },
  });
  if (!agentResp.ok()) {
    throw new Error(
      `seedPendingAccessRequest: create agent failed (${agentResp.status()}): ${await agentResp.text()}`,
    );
  }
  const agent = (await agentResp.json()) as { id?: string; agent_id?: string; api_key?: string };
  const agentId = agent.id ?? agent.agent_id ?? "";
  const apiKey = agent.api_key ?? "";
  if (!apiKey) {
    throw new Error(
      "seedPendingAccessRequest: agent creation did not return an Agent API Key " +
        `(keys: ${Object.keys(agent).join(", ")}) — cannot authenticate the MCP request_access call.`,
    );
  }

  // 3. MCP request_access as the agent — creates the pending kind=access row.
  const mcpResp = await request.post(`${MCP_URL}/v1/tools/request_access`, {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    data: { service_id: serviceId, action },
  });
  if (!mcpResp.ok()) {
    throw new Error(
      `seedPendingAccessRequest: MCP request_access failed (${mcpResp.status()}): ${await mcpResp.text()}`,
    );
  }
  const data = (await mcpResp.json()) as { request_id?: string; status?: string };
  if (!data.request_id || data.status !== "pending") {
    throw new Error(
      `seedPendingAccessRequest: unexpected MCP response: ${JSON.stringify(data)}`,
    );
  }

  return { requestId: data.request_id, agentId, serviceId, action };
}
