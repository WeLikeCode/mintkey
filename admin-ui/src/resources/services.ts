/**
 * AdminJS Services resource — T-1.2.3.
 *
 * READ via @adminjs/sql (direct DB, read-only role).
 * WRITE via signed admin-api requests (ADR-0014.5).
 *
 * Source: T-1.2.3; Req 3; ADR-0013; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { buildSignedRequest } from "../lib/signed-request.js";

const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";

export const ServicesResource: ResourceWithOptions = {
  resource: "services",
  options: {
    navigation: { name: "Services", icon: "Network" },
    listProperties: ["id", "name", "slug", "base_url", "auth_scheme", "status", "created_at"],
    editProperties: ["name", "slug", "base_url", "auth_scheme", "description", "openapi_url", "allow_internal_urls"],
    showProperties: ["id", "name", "slug", "base_url", "auth_scheme", "description", "openapi_url", "status", "current_key_version", "created_at", "updated_at"],
    filterProperties: ["name", "slug", "auth_scheme", "status"],
    actions: {
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          // All writes route through admin-api (ADR-0014.5)
          const { currentAdmin, record } = context;
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/services`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${jwt}`,
              },
              body: JSON.stringify(request.payload),
            }
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
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/services/${serviceId}`,
            {
              method: "PATCH",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${jwt}`,
              },
              body: JSON.stringify(request.payload),
            }
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
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/services/${serviceId}`,
            {
              method: "DELETE",
              headers: { Authorization: `Bearer ${jwt}` },
            }
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
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.params.recordId;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/services/${serviceId}/test`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${jwt}`,
              },
              body: JSON.stringify({ method: "GET", path: "/health", timeout_ms: 5000 }),
            }
          );

          const result = await resp.json() as { ok: boolean; status_code?: number; latency_ms?: number };
          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: {
              message: result.ok
                ? `Test passed: ${result.status_code} in ${result.latency_ms}ms`
                : `Test failed: ${result.status_code}`,
              type: result.ok ? "success" : "error",
            },
          };
        },
      },
    },
  },
};
