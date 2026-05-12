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

const _servicesResource = new RestResource({
  id: "services", name: "Services",
  listPath: "/v1/tenants/{tenantId}/services",
  getPath: "/v1/tenants/{tenantId}/services/{id}",
  listKey: "services",
  idField: "id",
  properties: [
    { path: "id", type: "uuid", isId: true },
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
    filterProperties: ["name", "slug", "auth_scheme", "status"],
    properties: {
      auth_scheme: {
        availableValues: AUTH_SCHEMES,
      },
    },
    actions: {
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          const { resource, currentAdmin, record } = context;
          // AdminJS calls handler on GET to get the empty form record
          if (request.method === "get") {
            const emptyRecord = await resource.build({});
            return { record: emptyRecord.toJSON(currentAdmin) };
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
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to create service", type: "error" },
            };
          }

          return { record: record?.toJSON(currentAdmin) ?? {}, redirectUrl: "/admin/resources/services" };
        },
      },
      edit: {
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          // AdminJS calls GET to load the current record into the edit form
          if (request.method === "get") {
            return { record: record?.toJSON(currentAdmin) ?? {} };
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
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to update service", type: "error" },
            };
          }
          return { record: record?.toJSON(currentAdmin) ?? {} };
        },
      },
      delete: {
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}`,
            "DELETE"
          );

          return { record: record?.toJSON(currentAdmin) ?? {} };
        },
      },
      testService: {
        actionType: "record",
        label: "Test Connection",
        icon: "Activity",
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}/test`,
            "POST",
            { method: "GET", path: "/health", timeout_ms: 5000 }
          );

          const result = await resp.json() as { ok: boolean; status_code?: number; latency_ms?: number };
          return {
            record: record?.toJSON(currentAdmin) ?? {},
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
