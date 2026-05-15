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
import { AUTH_SCHEMES, getCredentialFields } from "../../lib/auth-scheme.js";

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
      const credPayload: Record<string, string> = {
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
                <Input
                  id={f.name}
                  type={f.type === "url" ? "url" : "text"}
                  value={credFields[f.name] ?? ""}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCredField(f.name, e.target.value)}
                  placeholder={f.placeholder ?? ""}
                  style={inputStyle}
                  data-testid={`field-input-${f.name}`}
                />
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
