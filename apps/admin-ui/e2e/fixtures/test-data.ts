/**
 * Test-data helpers — create and destroy entities via admin-api.
 *
 * Tests use these to set up known state before each test, then
 * enqueue cleanup entries for global teardown.
 *
 * Environment variables:
 *   ADMIN_API_URL   — defaults to http://localhost:8080
 *   PLAYWRIGHT_API_JWT — signed JWT with PlatformAdmin claims for cleanup calls
 */

import { recordCleanup, type CleanupEntry } from "./cleanup.js";
import { getApiSession } from "./session.js";
import { ADMIN_API } from "../env.js";

const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const PLAYWRIGHT_PASS = process.env.PLAYWRIGHT_PASS ?? "";

// ── Session cache ────────────────────────────────────────────────────────────

interface Session { sessionToken: string; csrfToken: string }

async function getSession(): Promise<Session | null> {
  return getApiSession();
}

// ── Minimal helper: POST with JSON ──────────────────────────────────────────

async function apiPost(path: string, body: unknown, _token?: string): Promise<Response> {
  const session = await getSession();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (session) {
    headers["Cookie"] = `mintkey_session=${session.sessionToken}; csrf_token=${session.csrfToken}`;
    headers["X-Mintkey-Csrf"] = session.csrfToken;
  }
  return fetch(`${ADMIN_API}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
}

// ── Enqueue cleanup ─────────────────────────────────────────────────────────

function enqueueCleanup(entry: CleanupEntry) {
  _cleanupQueue.push(entry);
  recordCleanup(entry); // persisted for global-teardown (see fixtures/cleanup.ts)
}

let _cleanupQueue: CleanupEntry[] = [];

export function getCleanupQueue(): CleanupEntry[] {
  return _cleanupQueue;
}

/** Clears the in-memory view only; the persisted queue is consumed by global-teardown. */
export function resetCleanupQueue() {
  _cleanupQueue = [];
}

// ── Entity factories (return IDs for later cleanup) ─────────────────────────

export async function createTestService(opts: {
  tenantId: string;
  name: string;
  slug?: string;
  baseUrl?: string;
  authScheme?: string;
}, token?: string): Promise<string> {
  // admin-api derives the slug from the name and ignores a `slug` in the body, and the
  // (tenant, slug) pair is unique (a duplicate currently surfaces as an HTTP 500). A fixed
  // name therefore breaks on any retry or re-run against the same database, so every test
  // service gets a unique suffix; callers that assert on the name use `toContainText`.
  const unique = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  const name = `${opts.name}-${unique}`;
  const slug = opts.slug ?? name.toLowerCase().replace(/\s+/g, "-");
  const resp = await apiPost(
    `/v1/tenants/${opts.tenantId}/services`,
    { name, slug, base_url: opts.baseUrl ?? "https://example.com", auth_scheme: opts.authScheme ?? "api_key_header" },
    token
  );
  if (!resp.ok) throw new Error(`createTestService(${name}) failed: HTTP ${resp.status} ${await resp.text()}`);
  const data = await resp.json() as { id?: string; service_id?: string };
  const id = data.id ?? data.service_id ?? "";
  enqueueCleanup({ method: "DELETE", url: `/v1/tenants/${opts.tenantId}/services/${id}` });
  return id;
}

export async function createTestAgent(opts: {
  tenantId: string;
  name: string;
  description?: string;
}, token?: string): Promise<{ agentId: string; apiKey: string }> {
  const resp = await apiPost(
    `/v1/tenants/${opts.tenantId}/agents`,
    { name: opts.name, description: opts.description ?? "" },
    token
  );
  const data = await resp.json() as { id?: string; agent_id?: string; api_key?: string };
  const agentId = data.id ?? data.agent_id ?? "";
  enqueueCleanup({ method: "DELETE", url: `/v1/tenants/${opts.tenantId}/agents/${agentId}` });
  return { agentId, apiKey: data.api_key ?? "" };
}

export async function createTestCredential(opts: {
  tenantId: string;
  serviceId: string;
  authScheme: string;
  plaintext: string;
}, token?: string): Promise<string> {
  const resp = await apiPost(
    `/v1/tenants/${opts.tenantId}/services/${opts.serviceId}/credentials`,
    { auth_scheme: opts.authScheme, value: opts.plaintext },  // admin-api field is "value", not "plaintext"
    token
  );
  const data = await resp.json() as { id?: string; credential_id?: string };
  return data.id ?? data.credential_id ?? "";
}

export async function createTestPermission(opts: {
  tenantId: string;
  agentId: string;
  serviceId: string;
  action: string;
  constraints?: Record<string, unknown>;
}, token?: string): Promise<string> {
  // The flat POST /v1/tenants/{tid}/permissions answers 405; grants are created agent-scoped.
  const resp = await apiPost(
    `/v1/tenants/${opts.tenantId}/agents/${opts.agentId}/permissions`,
    { service_id: opts.serviceId, action: opts.action, constraints: opts.constraints ?? {} },
    token
  );
  if (!resp.ok) throw new Error(`createTestPermission failed: HTTP ${resp.status} ${await resp.text()}`);
  const data = await resp.json() as { id?: string; permission_id?: string };
  const permId = data.id ?? data.permission_id ?? "";
  enqueueCleanup({ method: "DELETE", url: `/v1/tenants/${opts.tenantId}/permissions/${permId}` });
  return permId;
}

export async function revokeAgent(tenantId: string, agentId: string, token?: string): Promise<Response> {
  return apiPost(`/v1/tenants/${tenantId}/agents/${agentId}/revoke`, {}, token);
}

export async function revokeApiKey(tenantId: string, agentId: string, keyId: string, token?: string): Promise<Response> {
  return apiPost(`/v1/tenants/${tenantId}/agents/${agentId}/api-keys/${keyId}/revoke`, { reason: "test_cleanup" }, token);
}

export async function rotateCredential(tenantId: string, serviceId: string, credentialId: string, newPlaintext: string, token?: string): Promise<Response> {
  return apiPost(
    `/v1/tenants/${tenantId}/services/${serviceId}/credentials`,
    { rotate_from: credentialId, plaintext: newPlaintext },
    token
  );
}

export async function getAuditEvents(tenantId: string, token?: string): Promise<any[]> {
  const resp = await fetch(`${ADMIN_API}/v1/tenants/${tenantId}/audit`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await resp.json();
  return data.events ?? data.audit ?? [];
}

export async function createTestTenant(name: string = "test-tenant", token?: string): Promise<{ tenantId: string; slug: string }> {
  const slug = name.toLowerCase().replace(/\s+/g, "-") + "-" + Date.now();
  const resp = await apiPost("/v1/tenants", { slug, display_name: name }, token);
  const data = await resp.json();
  enqueueCleanup({ method: "DELETE", url: `/v1/tenants/${data.id}` });
  return { tenantId: data.id, slug };
}