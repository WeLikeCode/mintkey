/**
 * AdminJS Services resource — T-1.2.3.
 *
 * READ via RestResource (calls admin-api HTTP).
 * WRITE via apiWrite (session + CSRF double-submit, server-to-server).
 *
 * Source: T-1.2.3; Req 3; ADR-0013; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { AUTH_SCHEMES } from "../lib/auth-scheme.js";
import { apiWrite } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

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
  ],
});

export const ServicesResource: ResourceWithOptions & { adminResource: typeof _servicesResource } = {
  resource: _servicesResource.resource,
  adminResource: _servicesResource,
  options: {
    navigation: { name: "Services", icon: "Network" },
    listProperties: ["id", "name", "slug", "base_url", "auth_scheme", "status", "created_at"],
    editProperties: ["name", "slug", "base_url", "auth_scheme", "description", "openapi_url"],
    showProperties: ["id", "name", "slug", "base_url", "auth_scheme", "description", "openapi_url", "status", "current_key_version", "created_at", "updated_at"],
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
    },
    actions: {
      list: {
        component: Components.ServicesIntro,
      },
      new: {
        isVisible: true,
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

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to create service", type: "error" },
            };
          }

          return { record: await recordJSON(context, request.payload ?? {}), redirectUrl: "/admin/resources/services" };
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
      testService: {
        actionType: "record",
        label: "Test Connection",
        icon: "Activity",
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}/test`,
            "POST",
            { method: "GET", path: "/health", timeout_ms: 5000 }
          );

          const result = await resp.json() as { ok: boolean; status_code?: number; latency_ms?: number };
          return {
            record: await recordJSON(context),
            notice: {
              message: result.ok
                ? `✓ ${result.status_code} OK · ${result.latency_ms}ms`
                : `✗ ${result.status_code} · failed`,
              type: result.ok ? "success" : "error",
            },
          };
        },
      },
    },
  },
};
