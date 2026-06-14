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
  // Typeahead combobox for email_service_id — fetches from email_services resource (feat/email-perm-grants-pickers)
  EmailServiceCombobox: componentLoader.add("EmailServiceCombobox", "./properties/EmailServiceCombobox"),
  // Template picker — browse + pick a service template before creating (OPS-S)
  ServiceTemplatePicker: componentLoader.add("ServiceTemplatePicker", "./actions/ServiceTemplatePicker"),
  // Copyable value — monospace code block + copy-to-clipboard button (OPS-X)
  CopyableValue: componentLoader.add("CopyableValue", "./properties/CopyableValue"),
  // Credential missing warning — red callout on service show page when no credential configured (UX-FB-B)
  CredentialMissingWarning: componentLoader.add("CredentialMissingWarning", "./properties/CredentialMissingWarning"),
  // Agent created notice — show-once API key screen with Copy buttons (OPS-DDEE DD-2)
  AgentCreatedNotice: componentLoader.add("AgentCreatedNotice", "./actions/AgentCreatedNotice"),
  // Credential new form — pre-fills service_id from URL query param (OPS-DDEE DD-1)
  CredentialNewForm: componentLoader.add("CredentialNewForm", "./actions/CredentialNewForm"),
  // Redirect action — immediately redirects to record.params.redirectTo URL (OPS-DDEE DD-1)
  RedirectAction: componentLoader.add("RedirectAction", "./actions/RedirectAction"),
  // Agent grants warning panel — red callout on show page when agent has zero grants (UX-FB-CE Part C)
  AgentGrantsWarningPanel: componentLoader.add("AgentGrantsWarningPanel", "./sections/AgentGrantsWarningPanel"),
  // Agent key expiry display — relative + absolute display for api_key_expires_at (UX-FB-AK-2)
  AgentExpiryDisplay: componentLoader.add("AgentExpiryDisplay", "./properties/AgentExpiryDisplay"),
  // Agent key rotated notice — hard-cutover rotation form + show-once result screen (UX-FB-AK-2)
  AgentKeyRotatedNotice: componentLoader.add("AgentKeyRotatedNotice", "./actions/AgentKeyRotatedNotice"),
  // Email service OAuth2 setup — authorize/re-authorize widget on show page (C-10)
  EmailServiceOAuth2Setup: componentLoader.add("EmailServiceOAuth2Setup", "./actions/EmailServiceOAuth2Setup"),
  // Email service credential form — username+password for email_password/email_app_password (feat/email-credentials-and-ui-fixes)
  EmailServiceCredentialForm: componentLoader.add("EmailServiceCredentialForm", "./actions/EmailServiceCredentialForm"),
  // Email service new form — provider-driven prefill for IMAP/SMTP host+port (Bug-B fix)
  EmailServiceNewForm: componentLoader.add("EmailServiceNewForm", "./actions/EmailServiceNewForm"),
  // Agent secret create form with reveal-once panel (Chunk C6, D11)
  AgentSecretNewForm: componentLoader.add("AgentSecretNewForm", "./actions/AgentSecretNewForm"),
};

// Global override: show-page renderer that inlines property.description below
// each value (UX-CLARITY chunk G). Uses override() not add() because
// DefaultShowProperty is one of AdminJS's defaultComponents.
componentLoader.override(
  "DefaultShowProperty",
  "./properties/DescriptiveShowProperty"
);
