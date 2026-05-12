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

const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";

// ── Minimal helper: POST with JSON ──────────────────────────────────────────

async function apiPost(path: string, body: unknown, token?: string): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(`${ADMIN_API}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
}

// ── Enqueue cleanup ─────────────────────────────────────────────────────────

interface CleanupEntry { method: "DELETE"; url: string }

const CLEANUP_FILE = "./tests/_cleanup.json";

function enqueueCleanup(entry: CleanupEntry) {
  _cleanupQueue.push(entry);
}

let _cleanupQueue: CleanupEntry[] = [];

export function getCleanupQueue(): CleanupEntry[] {
  return _cleanupQueue;
}

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
  const slug = opts.slug ?? opts.name.toLowerCase().replace(/\s+/g, "-");
  const resp = await apiPost(
    `/v1/tenants/${opts.tenantId}/services`,
    { name: opts.name, slug, base_url: opts.baseUrl ?? "https://example.com", auth_scheme: opts.authScheme ?? "api_key_header" },
    token
  );
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
    { auth_scheme: opts.authScheme, plaintext: opts.plaintext },
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
  const resp = await apiPost(
    `/v1/tenants/${opts.tenantId}/permissions`,
    { agent_id: opts.agentId, service_id: opts.serviceId, action: opts.action, constraints: opts.constraints ?? {} },
    token
  );
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