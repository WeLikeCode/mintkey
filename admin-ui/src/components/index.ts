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
  // Inline search list — prominent search input above each resource list table (UX-B)
  InlineSearchList: componentLoader.add("InlineSearchList", "./list/InlineSearchList"),
  // JSON property renderer (fix-show-page-react-31)
  JsonValue: componentLoader.add("JsonValue", "./properties/JsonValue"),
  // Generic "confirm before executing" page for destructive record actions
  ConfirmAction: componentLoader.add("ConfirmAction", "./actions/ConfirmAction"),
  // Service API key show-once create flow (ADR-0018; R1 action-grid remediation)
  ApiKeyCreate: componentLoader.add("ApiKeyCreate", "./actions/ApiKeyCreate"),
  // Service create form with bundled credential + test CTA (UX-C6)
  ServiceCreateForm: componentLoader.add("ServiceCreateForm", "./actions/ServiceCreateForm"),
  // Test Service form — 5-field form + curl preview + result panel (UX-CLARITY P0)
  TestServiceForm: componentLoader.add("TestServiceForm", "./actions/TestServiceForm"),
  // Tenant show page: associated services panel (UX-E)
  TenantServicesPanel: componentLoader.add("TenantServicesPanel", "./sections/TenantServicesPanel"),
  // Credential show page: intro panel with service link + audit link (OPS-Y)
  CredentialShowPanel: componentLoader.add("CredentialShowPanel", "./sections/CredentialShowPanel"),
  // Typeahead combobox property components — agent_id + service_id pickers (UX-A)
  AgentCombobox: componentLoader.add("AgentCombobox", "./properties/AgentCombobox"),
  ServiceCombobox: componentLoader.add("ServiceCombobox", "./properties/ServiceCombobox"),
  // Template picker — browse + pick a service template before creating (OPS-S)
  ServiceTemplatePicker: componentLoader.add("ServiceTemplatePicker", "./actions/ServiceTemplatePicker"),
  // Copyable value — monospace code block + copy-to-clipboard button (OPS-X)
  CopyableValue: componentLoader.add("CopyableValue", "./properties/CopyableValue"),
};

// Global override: show-page renderer that inlines property.description below
// each value (UX-CLARITY chunk G). Uses override() not add() because
// DefaultShowProperty is one of AdminJS's defaultComponents.
componentLoader.override(
  "DefaultShowProperty",
  "./properties/DescriptiveShowProperty"
);
