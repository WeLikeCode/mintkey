/**
 * Mintkey custom dashboard — replaces the default AdminJS landing.
 *
 * The handler queries admin-api for counts (services, agents, permissions,
 * audit events in last 24h) and computes a quick-start checklist state.
 *
 * Source: ADMIN_UI_SPEC.md §2.1; T-1.1.4; ADR-0013; ADR-0014.5.
 */

const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";

export interface DashboardChecklist {
  hasServices: boolean;
  hasCredentials: boolean;
  hasAgents: boolean;
  hasPermissions: boolean;
  hasTested: boolean;
}

export interface DashboardData {
  email: string;
  tenantId: string;
  servicesCount: number;
  agentsCount: number;
  permissionsCount: number;
  auditCount24h: number;
  checklist: DashboardChecklist;
}

/**
 * dashboardHandler — called by AdminJS as the dashboard handler.
 * Returns DashboardData for the React component to render.
 */
export async function dashboardHandler(
  _request: unknown,
  _response: unknown,
  context: { currentAdmin: { tenantId?: string; email?: string } }
): Promise<DashboardData> {
  const tenantId = context.currentAdmin?.tenantId ?? "";
  const email = context.currentAdmin?.email ?? "";

  const empty: DashboardData = {
    email,
    tenantId,
    servicesCount: 0,
    agentsCount: 0,
    permissionsCount: 0,
    auditCount24h: 0,
    checklist: {
      hasServices: false,
      hasCredentials: false,
      hasAgents: false,
      hasPermissions: false,
      hasTested: false,
    },
  };

  if (!tenantId) return empty;

  try {
    const [svcResp, agentResp, permResp, auditResp] = await Promise.allSettled([
      fetch(`${ADMIN_API_URL}/v1/tenants/${tenantId}/services`),
      fetch(`${ADMIN_API_URL}/v1/tenants/${tenantId}/agents`),
      fetch(`${ADMIN_API_URL}/v1/tenants/${tenantId}/permissions`),
      fetch(`${ADMIN_API_URL}/v1/tenants/${tenantId}/audit`),
    ]);

    const services = svcResp.status === "fulfilled" && svcResp.value.ok
      ? ((await svcResp.value.json()) as { services?: unknown[] }).services ?? []
      : [];

    const agents = agentResp.status === "fulfilled" && agentResp.value.ok
      ? ((await agentResp.value.json()) as { agents?: unknown[] }).agents ?? []
      : [];

    const permissions = permResp.status === "fulfilled" && permResp.value.ok
      ? ((await permResp.value.json()) as { permissions?: unknown[] }).permissions ?? []
      : [];

    // admin-api's audit list envelope is { items: [...], next_cursor }.
    const events = auditResp.status === "fulfilled" && auditResp.value.ok
      ? ((await auditResp.value.json()) as { items?: unknown[] }).items ?? []
      : [];

    // hasCredentials: any service with current_key_version > 0
    const hasCredentials = (services as Array<{ current_key_version?: number }>)
      .some((s) => (s.current_key_version ?? 0) > 0);

    // hasTested: any service with last_test field set
    const hasTested = (services as Array<{ last_test?: unknown }>)
      .some((s) => s.last_test != null);

    return {
      email,
      tenantId,
      servicesCount: services.length,
      agentsCount: agents.length,
      permissionsCount: permissions.length,
      auditCount24h: events.length,
      checklist: {
        hasServices: services.length > 0,
        hasCredentials,
        hasAgents: agents.length > 0,
        hasPermissions: permissions.length > 0,
        hasTested,
      },
    };
  } catch {
    return empty;
  }
}
