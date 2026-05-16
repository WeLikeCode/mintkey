/**
 * AdminJS Credentials resource — T-1.3.4 + T-1.8.4.
 *
 * READ: list credentials via RestResource.
 * WRITE: create/rotate via apiWrite (session + CSRF, ADR-0014.5).
 *
 * Plaintext credential never appears in the UI (ADR-0014.4, S-SEC-1).
 *
 * Source: T-1.3.4; T-1.8.4; Req 4; ADR-0013; ADR-0014.4; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { buildCredentialPayload } from "../lib/auth-scheme.js";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

const _credentialsResource = new RestResource({
  id: "credentials", name: "Credentials",
  // The list path reuses the services endpoint — credentials are listed per
  // service. There is no tenant-wide credentials list endpoint; `q` here
  // matches service name/slug, giving an indirect "filter by service" UX.
  listPath: "/v1/tenants/{tenantId}/services",
  listKey: "services",
  idField: "id",
  filterKeys: ["q"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "service_id", type: "string" },
    { path: "name", type: "string" },
    { path: "slug", type: "string" },
    { path: "auth_scheme", type: "string" },
    { path: "current_key_version", type: "number" },
    { path: "status", type: "string" },
    // Virtual filter-only: free-text search on service name/slug
    { path: "q", type: "string" },
    // Virtual show-only: intro panel (service link + audit link + backlog note) (OPS-Y)
    { path: "_credentialShowPanel", type: "string" },
  ],
});

export const CredentialsResource: ResourceWithOptions & { adminResource: typeof _credentialsResource } = {
  resource: _credentialsResource.resource,
  adminResource: _credentialsResource,
  options: {
    navigation: { name: "Credentials", icon: "Lock" },
    // Service is first column per ADMIN_UI_SPEC.md §2.4
    listProperties: ["name", "auth_scheme", "current_key_version", "status"],
    showProperties: ["_credentialShowPanel", "id", "name", "slug", "auth_scheme", "current_key_version", "status"],
    editProperties: ["service_id", "auth_scheme"],
    filterProperties: ["q", "auth_scheme", "status"],
    properties: {
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (service name / slug)",
        description: "Case-insensitive substring match on service name and slug.",
      },
      // Renamed for clarity: the list is service-centric; "name" is the service name
      name: {
        label: "Service",
      },
      // Virtual show-page intro panel — renders above the property table (OPS-Y)
      _credentialShowPanel: {
        label: "About this credential",
        isVisible: { show: true, list: false, edit: false, new: false, filter: false },
        components: {
          show: Components.CredentialShowPanel,
        },
      },
    },
    actions: {
      list: {
        component: Components.CredentialsIntro,
      },
      // Create via admin-api (plaintext only sent once, never stored in AdminJS)
      // (OPS-DDEE DD-1) CredentialNewForm reads ?service_id= from URL and
      // pre-fills + disables the service_id field when arriving via Set Credential CTA.
      new: {
        isVisible: true,
        label: "Register Credential",
        component: Components.CredentialNewForm,
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const serviceId = request.payload?.service_id as string;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}/credentials`,
            "POST",
            buildCredentialPayload(
              request.payload?.auth_scheme as string ?? "none",
              request.payload as Record<string, string> ?? {}
            ),
            operatorOpts
          );

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to register credential", type: "error" },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: { message: "Credential registered", type: "success" },
            redirectUrl: "/admin/resources/credentials",
          };
        },
      },
      edit: { isVisible: false },
      delete: { isVisible: false },

      // T-1.8.4: Rotate action — R14a fix.
      // POSTs to the dedicated rotate endpoint (ADR-0013 §3.1).
      // serviceId is the wire-form svc_ ID from the record; admin-ui passes it
      // through without decoding (admin-api decodes — R12/R14a lesson).
      // credentialId (rotate_from) identifies the credential being superseded.
      rotateCredential: {
        actionType: "record",
        component: Components.ConfirmAction,
        label: "Rotate",
        icon: "RotateCw",
        isVisible: true,
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          // record.id is the service wire-form id (svc_…); the record here is a
          // service record (credentials list reuses services endpoint).
          const serviceId = record?.get("id") as string;
          // Group F fix: request.params.recordId is ALWAYS the service's svc_<Crockford>
          // wire form (credentials list is keyed on services). Sending it as rotate_from
          // would cause admin-api to decode it as a cred_ ID and find no match, breaking
          // rotation for every operator. Omit rotate_from entirely so the backend applies
          // its deterministic rule (highest key_version active for the scheme).
          // If a future UI flow genuinely passes a cred_<Crockford> ID (e.g. a picker),
          // gate it: only pass rotate_from when recordId starts with "cred_".
          const credentialId = request.params.recordId as string | undefined;
          const authScheme = record?.get("auth_scheme") as string ?? "bearer_token";
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/services/${serviceId}/credentials/rotate`,
            "POST",
            {
              auth_scheme: authScheme,
              // Only pass rotate_from when a genuine cred_ wire ID is available
              // (not the svc_ record key from the AdminJS credentials list).
              ...(credentialId?.startsWith("cred_") ? { rotate_from: credentialId } : {}),
            },
            operatorOpts
          );

          if (!resp.ok) {
            const errBody = await resp.json().catch(() => ({})) as { title?: string; detail?: string };
            const msg = errBody.title ?? errBody.detail ?? "Rotation failed";
            return {
              record: await recordJSON(context),
              notice: { message: msg, type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
            notice: { message: "Credential rotated successfully", type: "success" },
          };
        },
      },
    },
  },
};
