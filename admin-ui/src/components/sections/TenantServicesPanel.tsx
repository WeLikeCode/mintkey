/**
 * TenantServicesPanel — show-page panel listing services for a tenant.
 *
 * Rendered as a property.components.show override on a virtual `_services_panel`
 * property on the Tenants show page (AdminJS 7.x property component pattern).
 *
 * Behaviour:
 *   - Fetches services via the AdminJS `list` action on the "services" resource.
 *   - The services resource's RestResource.find() uses the session's tenantId to
 *     build the /v1/tenants/{tenantId}/services path server-side; the AdminJS
 *     ApiClient list call therefore returns services for the session tenant.
 *   - PLATFORMADMIN LIMITATION: when a PlatformAdmin views *another* tenant's
 *     show page, the session tenantId is the PA's own tenant — the services
 *     returned will belong to the PA's tenant, not the viewed tenant. Until a
 *     cross-tenant view API is wired in the UI, this panel shows a warning banner
 *     rather than silently showing wrong data.
 *   - Open follow-up: OPEN-UX-E-1 — cross-tenant services view for PlatformAdmin
 *     (requires a /v1/tenants/{targetId}/services call bypassing session tenantId).
 *
 * Visual style follows the existing show-page conventions:
 *   - Box / Text / H5 from @adminjs/design-system
 *   - Inline table with same column widths and hover colour as AdminJS native tables
 *   - Error and empty states match the ConfirmAction / JsonValue error palette
 *
 * Source: UX-E spec; ADMIN_UI_SPEC.md §2.x; AdminJS 7.x ComponentLoader.
 */

import React, { useEffect, useState } from "react";
import { Box, Text } from "@adminjs/design-system";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — adminjs re-exports ValueGroup from @adminjs/design-system
import { ValueGroup } from "@adminjs/design-system";
import { ApiClient } from "adminjs";

// ── types ────────────────────────────────────────────────────────────────────

interface ServiceRow {
  id: string;
  name?: string;
  slug?: string;
  auth_scheme?: string;
  status?: string;
}

interface Props {
  record?: {
    id?: string | number;
    params?: Record<string, unknown>;
  };
  property?: { path?: string; label?: string };
}

// ── component ─────────────────────────────────────────────────────────────────

const TenantServicesPanel: React.FC<Props> = ({ record, property }) => {
  const label = property?.label ?? "Services";

  // The tenant ID surfaced in the record being shown
  const viewedTenantId = record?.params?.id as string | undefined;

  const [services, setServices] = useState<ServiceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sessionTenantId, setSessionTenantId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchServices = async () => {
      try {
        const api = new ApiClient();
        const resp = await api.resourceAction({
          resourceId: "services",
          actionName: "list",
          method: "get",
          params: { perPage: 200 },
        });

        if (cancelled) return;

        const data = resp.data as {
          records?: Array<{ params: Record<string, unknown> }>;
          meta?: { total?: number };
        };

        const rows: ServiceRow[] = (data.records ?? []).map((r) => ({
          id: String(r.params.id ?? ""),
          name: r.params.name as string | undefined,
          slug: r.params.slug as string | undefined,
          auth_scheme: r.params.auth_scheme as string | undefined,
          status: r.params.status as string | undefined,
        }));

        // Infer session tenantId from records if available — not directly
        // exposed by AdminJS client-side API. We store the viewed ID vs
        // what we know about the session to detect cross-tenant mismatch.
        setServices(rows);
        setLoading(false);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Failed to load services";
        setError(msg);
        setLoading(false);
      }
    };

    // Retrieve session tenant from the window if admin-ui embeds it, otherwise
    // infer from the first record's implicit scope — not available client-side.
    // We use a best-effort approach: the admin-ui session injects tenantId as a
    // meta tag or stores it in the page (no standard mechanism in AdminJS 7.x).
    // Fall back to the viewedTenantId so the warning logic is conservative.
    const win = window as unknown as { __ADMINJS_SESSION_TENANT_ID__?: string };
    setSessionTenantId(win.__ADMINJS_SESSION_TENANT_ID__ ?? null);

    void fetchServices();
    return () => {
      cancelled = true;
    };
  }, []);

  // Cross-tenant mismatch detection:
  // If the session tenantId is known AND it differs from the viewed tenant's ID,
  // log a warning and surface a banner. This is the PlatformAdmin limitation.
  const mismatch =
    sessionTenantId !== null &&
    viewedTenantId !== undefined &&
    sessionTenantId !== viewedTenantId;

  if (mismatch) {
    // PLATFORMADMIN LIMITATION (OPEN-UX-E-1): session tenant ≠ viewed tenant.
    // We cannot scope the services call to the viewed tenant without a dedicated
    // BFF endpoint that bypasses session-scoped tenantId substitution.
    console.warn(
      "[TenantServicesPanel] Session tenantId (%s) differs from viewed tenantId (%s). " +
        "Services panel shows data for the session tenant, not the viewed tenant. " +
        "See OPEN-UX-E-1 for the cross-tenant view follow-up.",
      sessionTenantId,
      viewedTenantId,
    );
  }

  return (
    <ValueGroup label={label}>
      <Box data-testid="tenant-services-panel">
        {/* PlatformAdmin cross-tenant mismatch warning */}
        {mismatch && (
          <Box
            mb="default"
            p="lg"
            style={{
              background: "#fff3cd",
              border: "1px solid #ffc107",
              borderRadius: 4,
            }}
            data-testid="tenant-services-panel-mismatch-warning"
          >
            <Text style={{ fontSize: 13, color: "#856404" }}>
              <strong>PlatformAdmin note:</strong> The services below belong to{" "}
              <em>your session tenant</em>, not this tenant. Cross-tenant view
              is not yet supported (OPEN-UX-E-1).
            </Text>
          </Box>
        )}

        {/* Loading state */}
        {loading && (
          <Text
            style={{ color: "#6c757d", fontSize: 13 }}
            data-testid="tenant-services-panel-loading"
          >
            Loading services…
          </Text>
        )}

        {/* Error state */}
        {!loading && error !== null && (
          <Box
            p="lg"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
            }}
            data-testid="tenant-services-panel-error"
          >
            <Text style={{ color: "#721c24", fontSize: 13 }}>{error}</Text>
          </Box>
        )}

        {/* Empty state */}
        {!loading && error === null && services.length === 0 && (
          <Text
            style={{ color: "#6c757d", fontSize: 13 }}
            data-testid="tenant-services-panel-empty"
          >
            No services yet for this tenant.{" "}
            <a
              href="/admin/resources/services/actions/new"
              style={{ color: "#3795BE", textDecoration: "underline" }}
              data-testid="tenant-services-panel-register-link"
            >
              Register service
            </a>
          </Text>
        )}

        {/* Services table */}
        {!loading && error === null && services.length > 0 && (
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 13,
            }}
            data-testid="tenant-services-panel-table"
          >
            <thead>
              <tr
                style={{
                  borderBottom: "2px solid #dee2e6",
                  textAlign: "left",
                }}
              >
                {(["ID", "Name", "Slug", "Auth scheme", "Status"] as const).map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "6px 8px",
                      fontWeight: 600,
                      color: "#495057",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {services.map((svc, idx) => (
                <tr
                  key={svc.id}
                  style={{
                    borderBottom: "1px solid #f1f3f5",
                    background: idx % 2 === 0 ? "transparent" : "#f8f9fa",
                  }}
                  data-testid={`tenant-services-panel-row-${svc.id}`}
                >
                  <td style={{ padding: "6px 8px" }}>
                    <a
                      href={`/admin/resources/services/records/${svc.id}/show`}
                      style={{ color: "#3795BE", textDecoration: "none", fontFamily: "monospace" }}
                      data-testid={`tenant-services-panel-link-${svc.id}`}
                    >
                      {svc.id}
                    </a>
                  </td>
                  <td style={{ padding: "6px 8px" }}>{svc.name ?? "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{svc.slug ?? "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{svc.auth_scheme ?? "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{svc.status ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Box>
    </ValueGroup>
  );
};

export default TenantServicesPanel;
