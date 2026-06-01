/**
 * CredentialNewForm — custom new-credential action component (OPS-DDEE DD-1).
 *
 * Replaces the default AdminJS new form for the Credentials resource.
 *
 * Features:
 *   1. Reads `service_id` from URL query params (?service_id=<id>).
 *   2. If present, pre-fills and DISABLES the service_id field (operator chose
 *      the service via the "Set Credential" CTA on the service show page).
 *   3. Standard auth_scheme selector — dynamic fields via getCredentialFields().
 *   4. Submit via the existing credentials `new` action handler.
 *
 * Hard rules:
 *   - service_id field is disabled (not hidden) when pre-filled — operator can
 *     see which service they're adding a credential for.
 *   - auth_scheme dropdown values come from AUTH_SCHEMES constant.
 *   - plaintext credential value is never stored by admin-ui (handled in handler).
 *
 * Source: OPS-DDEE DD-1; ADMIN_UI_SPEC.md §2.4; ADR-0013.
 */

import React, { useState, useEffect } from "react";
import {
  Box,
  H3,
  Text,
  Button,
  Label,
  Input,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";
import { useSearchParams, useNavigate } from "react-router-dom";
import { AUTH_SCHEMES, getCredentialFields, type KvRow } from "../../lib/auth-scheme.js";

// ── types ────────────────────────────────────────────────────────────────────

// Props injected by AdminJS for resource-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

// ── helpers ──────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #dee2e6",
  borderRadius: 4,
  fontSize: 14,
  lineHeight: "1.5",
  boxSizing: "border-box",
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  background: "#fff",
};

const textareaStyle: React.CSSProperties = {
  ...inputStyle,
  minHeight: 80,
  resize: "vertical",
  fontFamily: "monospace",
};

interface FieldProps {
  id: string;
  label: string;
  required?: boolean;
  children: React.ReactNode;
}

const FieldRow = ({ id, label, required, children }: FieldProps): React.ReactElement => (
  <Box mb="default" data-testid={`field-${id}`}>
    <Label htmlFor={id} required={required}>{label}</Label>
    {children}
  </Box>
);

// ── KV editor for oauth2_password_grant credential_fields ────────────────────

interface KvEditorProps {
  rows: KvRow[];
  onChange: (rows: KvRow[]) => void;
}

const KvEditor = ({ rows, onChange }: KvEditorProps): React.ReactElement => {
  const updateKey = (idx: number, newKey: string) => {
    const next = rows.map((r, i) => i === idx ? { ...r, key: newKey } : r);
    onChange(next);
  };
  const updateValue = (idx: number, newVal: string) => {
    const next = rows.map((r, i) => i === idx ? { ...r, value: newVal } : r);
    onChange(next);
  };
  const removeRow = (idx: number) => {
    onChange(rows.filter((_, i) => i !== idx));
  };
  const addRow = () => {
    onChange([...rows, { key: "", value: "" }]);
  };

  return (
    <Box data-testid="kv-editor">
      {rows.map((row, idx) => (
        <Box
          key={idx}
          mb="default"
          style={{ display: "flex", gap: 8, alignItems: "center" }}
          data-testid={`kv-row-${idx}`}
        >
          <Input
            value={row.key}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => updateKey(idx, e.target.value)}
            placeholder="field name"
            style={{ ...inputStyle, width: "40%" }}
            data-testid={`kv-key-${idx}`}
          />
          <Input
            type="password"
            value={row.value}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => updateValue(idx, e.target.value)}
            placeholder="value"
            style={{ ...inputStyle, flex: 1 }}
            data-testid={`kv-value-${idx}`}
          />
          <button
            type="button"
            onClick={() => removeRow(idx)}
            style={{ padding: "4px 10px", cursor: "pointer", borderRadius: 4, border: "1px solid #dee2e6", background: "#f8f9fa" }}
            data-testid={`kv-remove-${idx}`}
            aria-label="Remove row"
          >
            ×
          </button>
        </Box>
      ))}
      <button
        type="button"
        onClick={addRow}
        style={{ padding: "4px 12px", cursor: "pointer", borderRadius: 4, border: "1px solid #0d6efd", background: "#e7f0ff", color: "#0d6efd", fontSize: 13 }}
        data-testid="kv-add-row"
      >
        + Add field
      </button>
    </Box>
  );
};

// ── CredentialNewForm ─────────────────────────────────────────────────────────

const CredentialNewForm = (props: Props): React.ReactElement => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // ── service_id — read from URL or allow manual entry ──────────────────────
  // When pre-filled via Set Credential CTA, disable editing.
  const [serviceId, setServiceId] = useState("");
  const [serviceIdLocked, setServiceIdLocked] = useState(false);

  // ── credential fields ──────────────────────────────────────────────────────
  const [authScheme, setAuthScheme] = useState("bearer_token");
  const [credFields, setCredFields] = useState<Record<string, string>>({});

  // ── oauth2_password_grant: editable key-value rows for credential_fields ───
  const [kvRows, setKvRows] = useState<KvRow[]>([{ key: "userName", value: "" }, { key: "password", value: "" }]);

  // ── submission state ───────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // ── on mount: read service_id from URL ────────────────────────────────────
  useEffect(() => {
    const urlServiceId = searchParams.get("service_id");
    if (urlServiceId) {
      setServiceId(urlServiceId);
      setServiceIdLocked(true); // operator chose this service via Set Credential CTA
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── derived ────────────────────────────────────────────────────────────────
  const schemeFields = getCredentialFields(authScheme);
  const hintFields = schemeFields.filter((f) => !f.secret);
  const secretFields = schemeFields.filter((f) => f.secret);

  const handleSchemeChange = (newScheme: string) => {
    setAuthScheme(newScheme);
    setCredFields({});
    setKvRows([{ key: "userName", value: "" }, { key: "password", value: "" }]);
  };

  const setCredField = (fieldName: string, value: string) => {
    setCredFields((prev) => ({ ...prev, [fieldName]: value }));
  };

  // ── submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!serviceId.trim()) {
      setError("Service ID is required.");
      return;
    }

    setSubmitting(true);
    setError(null);

    const api = new ApiClient();
    try {
      let credPayload: Record<string, string>;

      if (authScheme === "google_service_account") {
        credPayload = {
          auth_scheme: authScheme,
          service_id: serviceId.trim(),
          value: JSON.stringify({
            scheme: "google_service_account",
            service_account_json: credFields["service_account_json"] ?? "",
            scope: credFields["scope"] ?? "https://www.googleapis.com/auth/androidpublisher",
          }),
        };
      } else if (authScheme === "ssh_private_key") {
        credPayload = {
          auth_scheme: authScheme,
          service_id: serviceId.trim(),
          value: JSON.stringify({
            scheme: "ssh_private_key",
            private_key_pem: credFields["private_key_pem"] ?? "",
            target_address: credFields["target_address"] ?? "",
            ssh_user: credFields["ssh_user"] ?? "",
          }),
        };
      } else if (authScheme === "ssh_ca") {
        credPayload = {
          auth_scheme: authScheme,
          service_id: serviceId.trim(),
          value: JSON.stringify({
            scheme: "ssh_ca",
            ca_private_key_pem: credFields["ca_private_key_pem"] ?? "",
            ca_principal_prefix: credFields["ca_principal_prefix"] ?? "",
          }),
        };
      } else if (authScheme === "ssh_password") {
        credPayload = {
          auth_scheme: authScheme,
          service_id: serviceId.trim(),
          value: JSON.stringify({
            scheme: "ssh_password",
            username: credFields["username"] ?? "",
            password: credFields["password"] ?? "",
            target_address: credFields["target_address"] ?? "",
          }),
        };
      } else if (authScheme === "oauth2_password_grant") {
        // Assemble the value JSON per contract
        const credentialFields: Record<string, string> = {};
        for (const row of kvRows) {
          if (row.key.trim()) {
            credentialFields[row.key.trim()] = row.value;
          }
        }
        const tokenUrl = credFields["token_url"] ?? "";
        const tokenResponsePath = credFields["token_response_path"] || "$.access_token";
        const timeoutRaw = credFields["exchange_timeout_seconds"];
        const exchangeTimeoutSeconds = timeoutRaw ? parseInt(timeoutRaw, 10) : 10;

        const valueJson = JSON.stringify({
          token_url: tokenUrl,
          credential_fields: credentialFields,
          token_response_path: tokenResponsePath,
          exchange_timeout_seconds: exchangeTimeoutSeconds,
        });

        credPayload = {
          auth_scheme: authScheme,
          service_id: serviceId.trim(),
          value: valueJson,
          token_url: tokenUrl,
        };
      } else {
        credPayload = {
          auth_scheme: authScheme,
          service_id: serviceId.trim(),
          ...credFields,
        };

        // Remove empty optional fields so admin-api doesn't receive empty strings
        for (const key of Object.keys(credPayload)) {
          if (credPayload[key] === "" && key !== "value" && key !== "service_id") {
            delete credPayload[key];
          }
        }
      }

      const resp = await api.resourceAction({
        resourceId: "credentials",
        actionName: "new",
        method: "post",
        data: credPayload,
      });

      const result = resp.data as {
        notice?: { message: string; type: string };
        redirectUrl?: string;
      };

      if (result?.notice?.type === "error") {
        setError(result.notice.message || "Failed to register credential.");
        return;
      }

      setSuccess(true);

      // Navigate to credentials list after a short delay
      setTimeout(() => {
        navigate("/admin/resources/credentials");
      }, 1500);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSubmitting(false);
    }
  };

  // ── success state ──────────────────────────────────────────────────────────
  if (success) {
    return (
      <Box variant="white" p="xxl" data-testid="credential-new-form-success">
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#d4edda",
            border: "1px solid #c3e6cb",
            borderRadius: 4,
          }}
          data-testid="credential-success-banner"
        >
          <Text style={{ fontWeight: 600, color: "#155724" }}>
            Credential registered successfully. Redirecting to credentials list…
          </Text>
        </Box>
      </Box>
    );
  }

  // ── form ───────────────────────────────────────────────────────────────────
  return (
    <Box variant="white" p="xxl" data-testid="credential-new-form">
      <H3 mb="default">Register Credential</H3>

      {/* Pre-fill banner — shown when arriving from Set Credential CTA */}
      {serviceIdLocked && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#cce5ff",
            border: "1px solid #b8daff",
            borderRadius: 4,
          }}
          data-testid="credential-prefill-banner"
        >
          <Text style={{ color: "#004085" }}>
            Adding credential for service: <strong>{serviceId}</strong>
          </Text>
        </Box>
      )}

      <Text mb="xl" style={{ color: "#6c757d" }}>
        Register a credential for the selected service. The plaintext value is
        encrypted at rest — Mintkey never stores it in plain text.
      </Text>

      <form onSubmit={handleSubmit} noValidate>
        {/* Service ID */}
        <FieldRow id="service_id" label="Service ID" required>
          {serviceIdLocked ? (
            // Disabled — locked to the service chosen via Set Credential CTA
            <Box
              p="default"
              style={{
                background: "#e9ecef",
                border: "1px solid #dee2e6",
                borderRadius: 4,
                fontFamily: "monospace",
                fontSize: 14,
                color: "#495057",
                wordBreak: "break-all",
              }}
              data-testid="field-service-id-locked"
            >
              {serviceId}
              <input type="hidden" name="service_id" value={serviceId} />
            </Box>
          ) : (
            <Input
              id="service_id"
              value={serviceId}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setServiceId(e.target.value)}
              placeholder="svc_..."
              style={inputStyle}
              required
              data-testid="field-input-service_id"
            />
          )}
          {serviceIdLocked && (
            <Text style={{ fontSize: 12, color: "#6c757d", marginTop: 4 }}>
              Service is pre-selected. To change, navigate to a different service.
            </Text>
          )}
        </FieldRow>

        {/* Auth scheme */}
        <FieldRow id="auth_scheme" label="Auth scheme">
          <select
            id="auth_scheme"
            value={authScheme}
            onChange={(e) => handleSchemeChange(e.target.value)}
            style={selectStyle}
            data-testid="field-select-auth_scheme"
          >
            {AUTH_SCHEMES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </FieldRow>

        {/* Hint fields (non-secret, e.g. header_name, query_param) */}
        {hintFields.length > 0 && (
          <Box
            mt="lg"
            mb="default"
            p="lg"
            style={{
              background: "#f8f9fa",
              border: "1px solid #dee2e6",
              borderRadius: 4,
            }}
            data-testid="credential-hint-fields"
          >
            <Text mb="default" style={{ fontWeight: 600, color: "#495057" }}>
              {authScheme.replace(/_/g, " ")} settings
            </Text>
            {hintFields.map((f) => (
              <FieldRow key={f.name} id={f.name} label={f.label} required={f.required}>
                {f.type === "kv-editor" ? (
                  <KvEditor rows={kvRows} onChange={setKvRows} />
                ) : f.type === "number" ? (
                  <Input
                    id={f.name}
                    type="number"
                    value={credFields[f.name] ?? (f.defaultValue ?? "")}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCredField(f.name, e.target.value)}
                    placeholder={f.placeholder ?? f.defaultValue ?? ""}
                    style={inputStyle}
                    data-testid={`field-input-${f.name}`}
                    min={f.min}
                    max={f.max}
                  />
                ) : (
                  <Input
                    id={f.name}
                    type={f.type === "url" ? "url" : "text"}
                    value={credFields[f.name] ?? (f.defaultValue ?? "")}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCredField(f.name, e.target.value)}
                    placeholder={f.placeholder ?? ""}
                    style={inputStyle}
                    data-testid={`field-input-${f.name}`}
                  />
                )}
              </FieldRow>
            ))}
          </Box>
        )}

        {/* Secret fields (e.g. API key value) */}
        {secretFields.length > 0 && (
          <Box
            mt="lg"
            mb="default"
            p="lg"
            style={{
              background: "#fff",
              border: "1px solid #dee2e6",
              borderRadius: 4,
            }}
            data-testid="credential-secret-fields"
          >
            <Text mb="default" style={{ fontWeight: 600, color: "#495057" }}>
              Credential value
            </Text>
            {secretFields.map((f) => (
              <FieldRow key={f.name} id={f.name} label={f.label} required={f.required}>
                {f.type === "textarea" ? (
                  <textarea
                    id={f.name}
                    value={credFields[f.name] ?? ""}
                    onChange={(e) => setCredField(f.name, e.target.value)}
                    placeholder={f.placeholder ?? ""}
                    style={textareaStyle}
                    data-testid={`field-input-${f.name}`}
                  />
                ) : (
                  <Input
                    id={f.name}
                    type={f.type === "password" ? "password" : "text"}
                    value={credFields[f.name] ?? ""}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCredField(f.name, e.target.value)}
                    placeholder={f.placeholder ?? ""}
                    style={inputStyle}
                    data-testid={`field-input-${f.name}`}
                  />
                )}
              </FieldRow>
            ))}
          </Box>
        )}

        {/* Error display */}
        {error && (
          <Box
            mb="lg"
            p="lg"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
            }}
            data-testid="create-error"
          >
            <Text style={{ color: "#721c24" }}>{error}</Text>
          </Box>
        )}

        {/* Buttons */}
        <Box flex mt="xl" style={{ gap: 12 }}>
          <Button
            type="submit"
            variant="primary"
            disabled={submitting}
            data-testid="credential-new-submit"
          >
            {submitting ? "Registering…" : "Register Credential"}
          </Button>
          <Button
            as="a"
            href="/admin/resources/credentials"
            variant="light"
            data-testid="credential-new-cancel"
          >
            Cancel
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default CredentialNewForm;
