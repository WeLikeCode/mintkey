/**
 * TenantServicesPanel — show-page panel listing services for a tenant.
 *
 * Rendered as a property.components.show override on a virtual `_services_panel`
 * property on the Tenants show page (AdminJS 7.x property component pattern).
 *
 * Behaviour (UX-BL4):
 *   - On mount, compares the session tenantId (from useCurrentAdmin) with
 *     record.params.id (the viewed tenant).
 *   - Same tenant (operator viewing their own tenant show page):
 *       Uses the normal AdminJS list action on the "services" resource —
 *       existing behaviour unchanged.
 *   - Different tenant + PlatformAdmin:
 *       Calls the new `crossTenantServicesList` resource action on the "tenants"
 *       resource, passing tenant_id=<viewedTenantId> as a query parameter.
 *       The BFF action forwards X-Platform-Admin:true to admin-api, which lets
 *       RLS through to return the viewed tenant's services.
 *   - Different tenant + NOT PlatformAdmin:
 *       Shows an empty state — "You don't have access to this tenant's services".
 *       This path should not be reachable in practice (non-PAs can't view other
 *       tenants' show pages) but is handled defensively to avoid data leakage.
 *
 * The yellow cross-tenant mismatch warning banner from UX-E is removed — the
 * correct data is now shown instead (OPEN-UX-E-1 resolved by UX-BL4).
 *
 * Visual style follows the existing show-page conventions:
 *   - Box / Text from @adminjs/design-system
 *   - Inline table with same column widths and hover colour as AdminJS native tables
 *   - Error and empty states match the ConfirmAction / JsonValue error palette
 *
 * Source: UX-E spec; UX-BL4; ADMIN_UI_SPEC.md §2.x; AdminJS 7.x ComponentLoader.
 */

import React, { useEffect, useState } from "react";
import { Box, Text } from "@adminjs/design-system";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — adminjs re-exports ValueGroup from @adminjs/design-system
import { ValueGroup } from "@adminjs/design-system";
import { ApiClient, useCurrentAdmin } from "adminjs";

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

  // The tenant ID surfaced in the record being shown (the viewed tenant)
  const viewedTenantId = record?.params?.id as string | undefined;

  // Session operator from AdminJS Redux store — includes tenantId + isPlatformAdmin
  // set by auth.ts authenticate() and stored in the @adminjs/express session.
  const [currentAdmin] = useCurrentAdmin();
  const sessionTenantId = (currentAdmin as { tenantId?: string } | null)?.tenantId;
  const isPlatformAdmin = (currentAdmin as { isPlatformAdmin?: boolean } | null)?.isPlatformAdmin === true;

  const [services, setServices] = useState<ServiceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Determine which fetch path to use:
  //   "own"   — viewed tenant === session tenant → use standard list action
  //   "cross" — viewed tenant ≠ session tenant + PA → use crossTenantServicesList
  //   "deny"  — viewed tenant ≠ session tenant + not PA → block (empty state)
  //   "own"   — viewedTenantId or sessionTenantId unknown → fall back to standard list
  const fetchMode: "own" | "cross" | "deny" =
    viewedTenantId && sessionTenantId && viewedTenantId !== sessionTenantId
      ? isPlatformAdmin
        ? "cross"
        : "deny"
      : "own";

  useEffect(() => {
    let cancelled = false;

    if (fetchMode === "deny") {
      setLoading(false);
      return;
    }

    const fetchServices = async () => {
      try {
        const api = new ApiClient();
        let rows: ServiceRow[] = [];

        if (fetchMode === "cross") {
          // UX-BL4: call the BFF crossTenantServicesList action with the
          // viewed tenant's ID as a query param. The BFF action forwards
          // X-Platform-Admin:true to admin-api.
          const resp = await api.resourceAction({
            resourceId: "tenants",
            actionName: "crossTenantServicesList",
            method: "get",
            params: { tenant_id: viewedTenantId },
          });

          const data = resp.data as {
            services?: Array<Record<string, unknown>>;
            record?: { params?: { services?: Array<Record<string, unknown>>; error?: string } };
          };

          // The BFF returns the services array in two places:
          //   resp.data.services (top-level) and
          //   resp.data.record.params.services (AdminJS record envelope)
          // Try top-level first, fall back to record envelope.
          const rawServices = Array.isArray(data.services)
            ? data.services
            : Array.isArray(data.record?.params?.services)
              ? (data.record!.params!.services as Array<Record<string, unknown>>)
              : [];

          const errorMsg = data.record?.params?.error;
          if (typeof errorMsg === "string" && errorMsg) {
            if (!cancelled) {
              setError(errorMsg);
              setLoading(false);
            }
            return;
          }

          rows = rawServices.map((r) => ({
            id: String(r.id ?? ""),
            name: r.name as string | undefined,
            slug: r.slug as string | undefined,
            auth_scheme: r.auth_scheme as string | undefined,
            status: r.status as string | undefined,
          }));
        } else {
          // Standard path: list action scoped to session tenant
          const resp = await api.resourceAction({
            resourceId: "services",
            actionName: "list",
            method: "get",
            params: { perPage: 200 },
          });

          const data = resp.data as {
            records?: Array<{ params: Record<string, unknown> }>;
            meta?: { total?: number };
          };

          rows = (data.records ?? []).map((r) => ({
            id: String(r.params.id ?? ""),
            name: r.params.name as string | undefined,
            slug: r.params.slug as string | undefined,
            auth_scheme: r.params.auth_scheme as string | undefined,
            status: r.params.status as string | undefined,
          }));
        }

        if (cancelled) return;
        setServices(rows);
        setLoading(false);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Failed to load services";
        setError(msg);
        setLoading(false);
      }
    };

    void fetchServices();
    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchMode, viewedTenantId]);

  return (
    <ValueGroup label={label}>
      <Box data-testid="tenant-services-panel">

        {/* Loading state */}
        {loading && fetchMode !== "deny" && (
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

        {/* Denied: non-PA operator somehow viewing another tenant's page */}
        {fetchMode === "deny" && (
          <Text
            style={{ color: "#6c757d", fontSize: 13 }}
            data-testid="tenant-services-panel-empty"
          >
            You don{"'"}t have access to this tenant{"'"}s services.
          </Text>
        )}

        {/* Empty state */}
        {!loading && error === null && fetchMode !== "deny" && services.length === 0 && (
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
