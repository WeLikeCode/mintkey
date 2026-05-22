/**
 * Auth scheme configuration — dropdown options and conditional field definitions.
 *
 * Used by the Service form (auth_scheme dropdown) and the Credential create
 * form (conditional field rendering per scheme).
 *
 * Source: ADMIN_UI_SPEC.md §1.1; T-1.3.4; ADR-0014.4.
 */

export interface AuthSchemeOption {
  value: string;
  label: string;
}

export interface CredentialField {
  name: string;
  label: string;
  type: "text" | "password" | "textarea" | "url";
  secret: boolean;
  required: boolean;
  placeholder?: string;
}

export const AUTH_SCHEMES: AuthSchemeOption[] = [
  { value: "none", label: "None — no credential needed" },
  { value: "api_key_header", label: "API key — header" },
  { value: "api_key_query", label: "API key — query param" },
  { value: "bearer_token", label: "Bearer token" },
  { value: "basic_auth", label: "Basic auth (username + password)" },
  { value: "oauth2_client_credentials", label: "OAuth 2.0 — client credentials" },
  { value: "oidc_client_secret", label: "OIDC — client secret" },
  { value: "mtls", label: "mTLS — client certificate" },
];

const SCHEME_FIELDS: Record<string, CredentialField[]> = {
  none: [],

  api_key_header: [
    { name: "header_name", label: "Header name", type: "text", secret: false, required: true, placeholder: "X-API-Key" },
    { name: "value", label: "API key value", type: "password", secret: true, required: true },
  ],

  api_key_query: [
    { name: "param_name", label: "Query param name", type: "text", secret: false, required: true, placeholder: "api_key" },
    { name: "value", label: "API key value", type: "password", secret: true, required: true },
  ],

  bearer_token: [
    { name: "value", label: "Bearer token", type: "password", secret: true, required: true },
  ],

  basic_auth: [
    { name: "username", label: "Username", type: "text", secret: false, required: true },
    { name: "password", label: "Password", type: "password", secret: true, required: true },
  ],

  oauth2_client_credentials: [
    { name: "token_url", label: "Token URL", type: "url", secret: false, required: true, placeholder: "https://auth.example.com/oauth/token" },
    { name: "client_id", label: "Client ID", type: "text", secret: false, required: true },
    { name: "client_secret", label: "Client secret", type: "password", secret: true, required: true },
    { name: "scopes", label: "Scopes (space-separated)", type: "text", secret: false, required: false },
    { name: "audience", label: "Audience", type: "text", secret: false, required: false },
  ],

  oidc_client_secret: [
    { name: "issuer", label: "Issuer URL", type: "url", secret: false, required: true, placeholder: "https://auth.example.com" },
    { name: "client_id", label: "Client ID", type: "text", secret: false, required: true },
    { name: "client_secret", label: "Client secret", type: "password", secret: true, required: true },
    { name: "scopes", label: "Scopes (space-separated)", type: "text", secret: false, required: false },
  ],

  mtls: [
    { name: "client_cert_pem", label: "Client certificate (PEM)", type: "textarea", secret: false, required: true },
    { name: "client_key_pem", label: "Client private key (PEM)", type: "textarea", secret: true, required: true },
  ],
};

/**
 * Returns the credential fields required for a given auth_scheme.
 * Returns [] for unknown schemes (safe default — show nothing).
 */
export function getCredentialFields(scheme: string): CredentialField[] {
  return SCHEME_FIELDS[scheme] ?? [];
}

/**
 * Build the credential POST body for admin-api.
 * Adds auth_scheme plus all scheme-specific fields from the form data.
 */
export function buildCredentialPayload(
  scheme: string,
  formData: Record<string, string>
): Record<string, string> {
  const fields = getCredentialFields(scheme);
  const payload: Record<string, string> = { auth_scheme: scheme };
  for (const field of fields) {
    if (formData[field.name] !== undefined) {
      payload[field.name] = formData[field.name];
    }
  }
  return payload;
}
