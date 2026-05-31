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
  type: "text" | "password" | "textarea" | "url" | "kv-editor" | "number";
  secret: boolean;
  required: boolean;
  placeholder?: string;
  defaultValue?: string;
  min?: number;
  max?: number;
}

export const AUTH_SCHEMES: AuthSchemeOption[] = [
  { value: "none", label: "None — no credential needed" },
  { value: "api_key_header", label: "API key — header" },
  { value: "api_key_query", label: "API key — query param" },
  { value: "bearer_token", label: "Bearer token" },
  { value: "basic_auth", label: "Basic auth (username + password)" },
  { value: "oauth2_client_credentials", label: "OAuth 2.0 — client credentials" },
  { value: "oauth2_password_grant", label: "OAuth 2.0 — password grant (username/password → token)" },
  { value: "oidc_client_secret", label: "OIDC — client secret" },
  { value: "mtls", label: "mTLS — client certificate" },
  { value: "apple_jwt", label: "Apple JWT — .p8 key (App Store Connect)" },
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

  oauth2_password_grant: [
    { name: "token_url", label: "Token URL", type: "url", secret: false, required: true, placeholder: "https://auth.example.com/oauth2/token" },
    { name: "credential_fields", label: "Credential fields (key → value)", type: "kv-editor", secret: false, required: true },
    { name: "token_response_path", label: "Token response path (JSONPath)", type: "text", secret: false, required: true, placeholder: "$.access_token", defaultValue: "$.access_token" },
    { name: "exchange_timeout_seconds", label: "Exchange timeout (seconds)", type: "number", secret: false, required: false, defaultValue: "10", min: 1, max: 120 },
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

  apple_jwt: [
    { name: "p8_key_pem", label: "Apple .p8 PEM (PKCS#8 EC private key)", type: "textarea", secret: true, required: true, placeholder: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----" },
    { name: "key_id", label: "Key ID (kid)", type: "text", secret: false, required: true, placeholder: "TNRVKBLCWWTH" },
    { name: "issuer_id", label: "Issuer ID (iss)", type: "text", secret: false, required: true, placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
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
 * Key-value row type used by the oauth2_password_grant kv-editor.
 * Each row holds an editable key name and a (masked) value.
 */
export interface KvRow {
  key: string;
  value: string;
}

/**
 * Build the credential POST body for admin-api.
 * Adds auth_scheme plus all scheme-specific fields from the form data.
 *
 * For oauth2_password_grant, assembles the nested value JSON:
 *   { token_url, credential_fields: {<k>:<v>,...}, token_response_path, exchange_timeout_seconds }
 */
export function buildCredentialPayload(
  scheme: string,
  formData: Record<string, string>
): Record<string, string> {
  const fields = getCredentialFields(scheme);
  const payload: Record<string, string> = { auth_scheme: scheme };

  if (scheme === "apple_jwt") {
    const p8KeyPem = formData["p8_key_pem"] ?? "";
    const keyId = formData["key_id"] ?? "";
    const issuerId = formData["issuer_id"] ?? "";

    payload["value"] = JSON.stringify({
      scheme: "apple_jwt",
      p8_key_pem: p8KeyPem,
      key_id: keyId,
      issuer_id: issuerId,
    });
    return payload;
  }

  if (scheme === "oauth2_password_grant") {
    // formData carries:
    //   token_url, token_response_path, exchange_timeout_seconds (as strings)
    //   credential_fields_json (pre-serialised JSON string of the kv map)
    const tokenUrl = formData["token_url"] ?? "";
    const tokenResponsePath = formData["token_response_path"] || "$.access_token";
    const timeoutRaw = formData["exchange_timeout_seconds"];
    const exchangeTimeoutSeconds = timeoutRaw ? parseInt(timeoutRaw, 10) : 10;

    let credentialFields: Record<string, string> = {};
    try {
      credentialFields = JSON.parse(formData["credential_fields_json"] ?? "{}") as Record<string, string>;
    } catch {
      credentialFields = {};
    }

    const valueJson = JSON.stringify({
      token_url: tokenUrl,
      credential_fields: credentialFields,
      token_response_path: tokenResponsePath,
      exchange_timeout_seconds: exchangeTimeoutSeconds,
    });

    payload["value"] = valueJson;
    payload["token_url"] = tokenUrl;
    return payload;
  }

  for (const field of fields) {
    if (formData[field.name] !== undefined) {
      payload[field.name] = formData[field.name];
    }
  }
  return payload;
}
