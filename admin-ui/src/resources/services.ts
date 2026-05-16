/**
 * AdminJS Services resource — T-1.2.3.
 *
 * READ via RestResource (calls admin-api HTTP).
 * WRITE via apiWrite (session + CSRF double-submit, server-to-server).
 *
 * OPS-SUX additions:
 *   (S) template-list + template-detail resource actions (BFF passthrough to /v1/service-templates)
 *   (U) test-transient resource action (BFF passthrough to /v1/tenants/{tenantId}/services/test-transient)
 *   (X) proxy_url virtual property shown on service show page via CopyableValue
 *
 * Source: T-1.2.3; Req 3; ADR-0013; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { AUTH_SCHEMES } from "../lib/auth-scheme.js";
import { apiWrite, getApiSession } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

// (OPS-X) Read the proxy base URL at startup time (server-side only).
// Falls back to http://localhost:8000 for local dev (Kong proxy default port).
const MINTKEY_PROXY_URL = process.env.MINTKEY_PROXY_URL ?? "http://localhost:8000";

const _servicesResource = new RestResource({
  id: "services", name: "Services",
  listPath: "/v1/tenants/{tenantId}/services",
  getPath: "/v1/tenants/{tenantId}/services/{id}",
  listKey: "services",
  idField: "id",
  filterKeys: ["q"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "name", type: "string" },
    { path: "slug", type: "string" },
    { path: "base_url", type: "string" },
    { path: "auth_scheme", type: "string", availableValues: AUTH_SCHEMES },
    { path: "status", type: "string" },
    { path: "description", type: "string" },
    { path: "openapi_url", type: "string" },
    { path: "current_key_version", type: "number" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
    // Virtual filter-only: free-text search forwarded to admin-api ?q=
    { path: "q", type: "string" },
    // (OPS-X) Virtual synthetic property — computed at show time, not stored in DB
    { path: "proxy_url", type: "string" },
    // (UX-FB-B) Virtual warning — red callout rendered when no credential is configured
    { path: "_credential_warning", type: "string" },
  ],
  // (OPS-X) Inject proxy_url into each record so CopyableValue can render it
  recordTransform: (item: Record<string, unknown>): Record<string, unknown> => {
    const id = item.id as string | undefined;
    if (id) {
      item.proxy_url = `${MINTKEY_PROXY_URL}/v1/call/${id}/{path}`;
    }
    return item;
  },
});

export const ServicesResource: ResourceWithOptions & { adminResource: typeof _servicesResource } = {
  resource: _servicesResource.resource,
  adminResource: _servicesResource,
  options: {
    navigation: { name: "Services", icon: "Network" },
    listProperties: ["id", "name", "slug", "base_url", "auth_scheme", "status", "created_at"],
    editProperties: ["name", "slug", "base_url", "auth_scheme", "description", "openapi_url"],
    showProperties: ["_credential_warning", "id", "name", "slug", "base_url", "auth_scheme", "description", "openapi_url", "proxy_url", "status", "current_key_version", "created_at", "updated_at"],
    filterProperties: ["q", "name", "slug", "auth_scheme", "status"],
    properties: {
      auth_scheme: {
        availableValues: AUTH_SCHEMES,
      },
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (name / slug)",
        description: "Case-insensitive substring match on service name and slug.",
      },
      // (OPS-X) Virtual proxy URL — show only, not stored
      proxy_url: {
        isVisible: { show: true, list: false, edit: false, new: false, filter: false },
        label: "Proxy URL",
        description: "Agents and clients call this URL to invoke the service through the egress proxy. Replace `{path}` with the upstream API path.",
        components: {
          show: Components.CopyableValue,
        },
      },
      // (UX-FB-B) Virtual credential warning — renders red callout when no active credential
      _credential_warning: {
        type: "string",
        isVisible: { show: true, list: false, edit: false, new: false, filter: false },
        label: "",
        description: "Inline warning when no credential is configured",
        components: {
          show: Components.CredentialMissingWarning,
        },
      },
    },
    actions: {
      list: {
        component: Components.ServicesIntro,
      },
      new: {
        isVisible: true,
        component: Components.ServiceCreateForm,
        handler: async (request, response, context) => {
          const { currentAdmin } = context;
          // AdminJS calls handler on GET to get the empty form record
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const tenantId = (currentAdmin as { tenantId: string }).tenantId;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services`,
            "POST",
            request.payload
          );

          const body = await resp.json().catch(() => ({})) as { id?: string; title?: string };

          if (!resp.ok) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: body.title ?? "Failed to create service", type: "error" },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            redirectUrl: `/admin/resources/services/records/${body.id}/show`,
          };
        },
      },
      edit: {
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin } = context;
          // AdminJS calls GET to load the current record into the edit form
          if (request.method === "get") {
            return { record: await recordJSON(context, request.payload ?? {}) };
          }
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}`,
            "PATCH",
            request.payload
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to update service", type: "error" },
            };
          }
          return { record: await recordJSON(context, request.payload ?? {}) };
        },
      },
      delete: {
        isVisible: true,
        component: Components.ConfirmAction,
        handler: async (request, response, context) => {
          const { currentAdmin, h, resource } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}`,
            "DELETE"
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: await recordJSON(context),
              notice: { message: err.title ?? "Failed to delete service", type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
            redirectUrl: h.resourceUrl({ resourceId: resource._decorated?.id() ?? resource.id() }),
            notice: { message: "Service deleted", type: "success" },
          };
        },
      },
      // (OPS-S) Template picker — resource action that renders the template browser
      templates: {
        actionType: "resource",
        label: "Create from template",
        icon: "Template",
        isVisible: true,
        showInDrawer: false,
        component: Components.ServiceTemplatePicker,
        handler: async (request, _response, context) => {
          // GET: return an empty record so the component can mount
          return { record: await recordJSON(context, {}) };
        },
      },

      // (OPS-S) BFF passthrough: GET /v1/service-templates → JSON response
      "template-list": {
        actionType: "resource",
        isVisible: false,
        handler: async (request, _response, context) => {
          const session = await getApiSession();
          const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";

          const headers: Record<string, string> = {};
          if (session?.sessionToken) {
            headers["Cookie"] = `mintkey_session=${session.sessionToken}`;
          }

          try {
            const resp = await fetch(`${ADMIN_API_URL}/v1/service-templates`, { headers });
            if (!resp.ok) {
              const baseRecord = await recordJSON(context, {});
              return {
                record: { ...baseRecord, params: { ...baseRecord.params, templates: [] } },
              };
            }
            const data = await resp.json() as { templates?: unknown[] };
            const templates = Array.isArray(data.templates) ? data.templates : [];
            const baseRecord = await recordJSON(context, {});
            return {
              record: { ...baseRecord, params: { ...baseRecord.params, templates } },
              templates,
            };
          } catch {
            const baseRecord = await recordJSON(context, {});
            return {
              record: { ...baseRecord, params: { ...baseRecord.params, templates: [] } },
            };
          }
        },
      },

      // (OPS-S) BFF passthrough: GET /v1/service-templates/{slug} → template detail
      //
      // EE fix (OPS-DDEE): template fields are returned BOTH as a nested object
      // (record.params.template) AND as flat record.params entries
      // (record.params["template.description"], etc.).  The React useEffect in
      // ServiceCreateForm.tsx reads data?.template first (top-level), then falls back
      // to record.params.template.  Both carry the full 5-field object.
      // Additionally, each field is stored flat in params so the React component
      // can also read them via record.params["template.name"] etc. as a belt-and-suspenders
      // guarantee that description and openapi_url arrive on screen.
      "template-detail": {
        actionType: "resource",
        isVisible: false,
        handler: async (request, _response, context) => {
          const slug = (request.query?.slug as string | undefined) ?? "";
          const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";

          const session = await getApiSession();
          const headers: Record<string, string> = {};
          if (session?.sessionToken) {
            headers["Cookie"] = `mintkey_session=${session.sessionToken}`;
          }

          try {
            const resp = await fetch(`${ADMIN_API_URL}/v1/service-templates/${encodeURIComponent(slug)}`, { headers });
            if (!resp.ok) {
              const baseRecord = await recordJSON(context, {});
              return {
                record: { ...baseRecord, params: { ...baseRecord.params, template: null } },
              };
            }
            const raw = await resp.json() as Record<string, unknown>;
            // Normalise: ensure all 5 expected fields are present (even if undefined)
            const template = {
              slug: raw.slug ?? "",
              name: raw.name ?? "",
              display_name: raw.display_name ?? "",
              description: raw.description ?? "",
              base_url: raw.base_url ?? "",
              auth_scheme: raw.auth_scheme ?? "",
              openapi_url: raw.openapi_url ?? "",
              test_path: raw.test_path ?? "/health",
            };
            const baseRecord = await recordJSON(context, {});
            // Flat params belt-and-suspenders: React can read either the nested
            // template object OR the individual flat keys.
            return {
              record: {
                ...baseRecord,
                params: {
                  ...baseRecord.params,
                  template,
                  "template.slug": template.slug,
                  "template.name": template.name,
                  "template.description": template.description,
                  "template.base_url": template.base_url,
                  "template.auth_scheme": template.auth_scheme,
                  "template.openapi_url": template.openapi_url,
                  "template.test_path": template.test_path,
                },
              },
              template,
            };
          } catch {
            const baseRecord = await recordJSON(context, {});
            return {
              record: { ...baseRecord, params: { ...baseRecord.params, template: null } },
            };
          }
        },
      },

      // (OPS-U) BFF passthrough: POST /v1/tenants/{tenantId}/services/test-transient
      "test-transient": {
        actionType: "resource",
        isVisible: false,
        handler: async (request, _response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;

          // request.payload contains the TransientTestRequest shaped body
          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/test-transient`,
            "POST",
            request.payload
          );

          const testResult = await resp.json() as {
            ok: boolean;
            status_code?: number;
            latency_ms?: number;
            final_url?: string;
            response_body_truncated?: string;
            error?: string;
          };

          const baseRecord = await recordJSON(context, {});
          return {
            record: {
              ...baseRecord,
              params: {
                ...baseRecord.params,
                testResult,
              },
            },
            testResult,
          };
        },
      },

      // (OPS-DDEE DD-1) Set Credential CTA — redirects operator to credentials/new
      // pre-filled with this service's ID. Same operator-only gate as testService.
      //
      // Uses RedirectAction component because AdminJS record-action GET responses
      // do NOT automatically follow `redirectUrl` — the component calls
      // navigate(redirectTo) on mount to perform the SPA-side redirect.
      setCredential: {
        actionType: "record",
        label: "Set Credential",
        icon: "Key",
        isVisible: true,
        showInDrawer: false,
        component: Components.RedirectAction,
        handler: async (request, _response, context) => {
          const serviceId = request.params.recordId;
          const baseRecord = await recordJSON(context);
          return {
            record: {
              ...baseRecord,
              params: {
                ...baseRecord.params,
                // RedirectAction component reads this on mount and calls navigate()
                redirectTo: `/admin/resources/credentials/actions/new?service_id=${serviceId}`,
              },
            },
          };
        },
      },

      testService: {
        actionType: "record",
        label: "Test Connection",
        icon: "Activity",
        isVisible: true,
        component: Components.TestServiceForm,
        handler: async (request, response, context) => {
          // GET: form load — return the record so the React component can read
          // base_url from record.params (no side-effect).
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }

          // POST with no payload (e.g. empty form submit): fall through gracefully.
          if (!request.payload || !request.payload.method) {
            return { record: await recordJSON(context) };
          }

          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          // Thread operator-supplied payload directly — no hardcoded values.
          // request.payload contains: method, path, headers?, body?, timeout_ms
          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}/test`,
            "POST",
            request.payload
          );

          const testResult = await resp.json() as {
            ok: boolean;
            status_code?: number;
            latency_ms?: number;
            final_url?: string;
            response_body_truncated?: string;
            error?: string;
          };

          // Embed testResult in the record's params so the React component (option C)
          // can read it from response.data.record.params.testResult.
          const baseRecord = await recordJSON(context);
          return {
            record: {
              ...baseRecord,
              params: {
                ...baseRecord.params,
                testResult,
              },
            },
          };
        },
      },
    },
  },
};
