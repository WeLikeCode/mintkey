/**
 * AdminJS ComponentLoader for Mintkey's custom UI components.
 *
 * AdminJS only renders a custom dashboard *UI* when you register a bundled
 * React component via a ComponentLoader and pass it as `dashboard.component`
 * (a handler alone leaves the stock "Welcome on Board!" tips page). The
 * ComponentLoader is wired into the AdminJS instance in src/index.ts; AdminJS
 * bundles the registered .tsx files at startup (NODE_ENV=production).
 *
 * Source: ADMIN_UI_SPEC.md §2.1; AdminJS 7.x ComponentLoader.
 */

import { ComponentLoader } from "adminjs";

export const componentLoader = new ComponentLoader();

export const Components = {
  Dashboard: componentLoader.add("Dashboard", "./Dashboard"),
  // Per-resource intro wrappers (admin-ui-ux-uplift chunk)
  TenantsIntro: componentLoader.add("TenantsIntro", "./sections/TenantsIntro"),
  ServicesIntro: componentLoader.add("ServicesIntro", "./sections/ServicesIntro"),
  CredentialsIntro: componentLoader.add("CredentialsIntro", "./sections/CredentialsIntro"),
  AgentsIntro: componentLoader.add("AgentsIntro", "./sections/AgentsIntro"),
  PermissionsIntro: componentLoader.add("PermissionsIntro", "./sections/PermissionsIntro"),
  ApiKeysIntro: componentLoader.add("ApiKeysIntro", "./sections/ApiKeysIntro"),
  AuditIntro: componentLoader.add("AuditIntro", "./sections/AuditIntro"),
  // JSON property renderer (fix-show-page-react-31)
  JsonValue: componentLoader.add("JsonValue", "./properties/JsonValue"),
};
