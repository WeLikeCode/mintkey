/**
 * ServiceCreateForm — custom new-service action component (UX-C6).
 *
 * Replaces the default AdminJS new form for the Services resource.
 *
 * Features:
 *   1. Standard service fields (name, base_url, auth_scheme dropdown, description, openapi_url).
 *   2. Conditional auth-scheme-specific fields rendered via getCredentialFields().
 *      - api_key_header → header_name input
 *      - api_key_query  → query_param input
 *      - oauth2_client_credentials → token_url, client_id, client_secret, scopes, audience
 *   3. Optional inline credential entry ("Add a credential now?" checkbox → credential sub-form).
 *   4. Submit creates service first, then optionally creates the credential.
 *   5. Success state: banner with "Test connection" CTA.
 *
 * Hard rules:
 *   - auth_scheme dropdown values come from AUTH_SCHEMES constant.
 *   - getCredentialFields() from auth-scheme.ts drives the conditional fields.
 *   - header_name is passed to credential POST (vault stores + returns it).
 *   - If credential POST fails after service succeeds: warn, don't roll back service.
 *
 * Source: UX-C6; admin-ui-ux-uplift chunk; ADMIN_UI_SPEC.md §1.3.
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
import { useNavigate, useSearchParams } from "react-router-dom";
import { AUTH_SCHEMES, getCredentialFields } from "../../lib/auth-scheme.js";

// ── types ────────────────────────────────────────────────────────────────────

// Props injected by AdminJS for resource-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

type SuccessState = {
  serviceId: string;
  credentialCreated: boolean;
  credentialWarning?: string;
};

interface TestResult {
  ok: boolean;
  status_code?: number;
  latency_ms?: number;
  final_url?: string;
  response_body_truncated?: string;
  error?: string;
}

interface ServiceTemplate {
  slug: string;
  name: string;
  description?: string;
  base_url?: string;
  auth_scheme?: string;
  openapi_url?: string;
  test_path?: string;
}

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

// ── ServiceCreateForm ─────────────────────────────────────────────────────────

const ServiceCreateForm = (props: Props): React.ReactElement => {
  const { resource } = props as { resource: { id: string } };
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // ── service fields ─────────────────────────────────────────────────────────
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [authScheme, setAuthScheme] = useState("none");
  const [description, setDescription] = useState("");
  const [openapiUrl, setOpenapiUrl] = useState("");

  // ── template pre-fill state ────────────────────────────────────────────────
  const [templateName, setTemplateName] = useState<string | null>(null);

  // ── test path state (editable; pre-filled from template or defaults to /health) ─
  const [testPath, setTestPath] = useState("/health");

  // ── credential fields (dynamic per scheme) ─────────────────────────────────
  // Map of field name → value for scheme-specific hint fields (non-secret)
  // and the credential value field (secret).
  const [credFields, setCredFields] = useState<Record<string, string>>({});

  // ── inline credential toggle ────────────────────────────────────────────────
  const [addCredential, setAddCredential] = useState(false);

  // ── submission state ───────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<SuccessState | null>(null);

  // ── test-before-save state ─────────────────────────────────────────────────
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  // ── derived ────────────────────────────────────────────────────────────────
  const schemeFields = getCredentialFields(authScheme);
  // Separate secret (value) fields from injection-hint fields
  const hintFields = schemeFields.filter((f) => !f.secret);
  const secretFields = schemeFields.filter((f) => f.secret);

  // ── template pre-fill on mount ─────────────────────────────────────────────
  // Reads ?template=<slug> from URL and fetches template detail to pre-fill form.
  // HARD RULE: credential value (secret) is NEVER pre-filled from template.
  useEffect(() => {
    const slug = searchParams.get("template");
    if (!slug) return;

    const api = new ApiClient();
    api
      .resourceAction({
        resourceId: resource?.id ?? "services",
        actionName: "template-detail",
        method: "get",
        params: { slug },
      })
      .then((resp) => {
        const data = resp.data as {
          template?: ServiceTemplate;
          record?: { params?: Record<string, unknown> };
        };
        // Primary: top-level template object (BFF returns it directly).
        // Fallback A: record.params.template (nested object form).
        // Fallback B: flat record.params["template.*"] keys (EE belt-and-suspenders fix).
        const tpl: ServiceTemplate | null | undefined =
          data?.template ??
          (data?.record?.params?.["template"] as ServiceTemplate | undefined) ??
          null;

        const flatParams = data?.record?.params ?? {};

        // Helper to get a field: prefer nested tpl object, then flat param key
        const getField = (key: keyof ServiceTemplate): string => {
          const fromTpl = tpl?.[key] as string | undefined;
          if (fromTpl) return fromTpl;
          const flat = flatParams[`template.${key}`] as string | undefined;
          return flat ?? "";
        };

        const hasAnyField =
          tpl != null ||
          Object.keys(flatParams).some((k) => k.startsWith("template."));

        if (!hasAnyField) return;

        // Pre-fill service fields from template (EE fix: all 5 fields)
        const tName = getField("name");
        const tBaseUrl = getField("base_url");
        const tAuthScheme = getField("auth_scheme");
        const tDescription = getField("description");
        const tOpenapiUrl = getField("openapi_url");

        if (tName) setName(tName);
        if (tBaseUrl) setBaseUrl(tBaseUrl);
        if (tAuthScheme) setAuthScheme(tAuthScheme);
        if (tDescription) setDescription(tDescription);
        if (tOpenapiUrl) setOpenapiUrl(tOpenapiUrl);

        // Pre-fill test path from template; fall back to /health if absent.
        const tTestPath = (tpl?.test_path as string | undefined)
          ?? (flatParams["template.test_path"] as string | undefined)
          ?? "";
        setTestPath(tTestPath || "/health");

        // DO NOT pre-fill credential value — security boundary (OPS-SUX hard rule)
        setCredFields({}); // ensure cred fields reset (no leakage)

        setTemplateName(tName || slug);
      })
      .catch(() => {
        // Template fetch failed — silently proceed with blank form
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run once on mount only

  // ── test-before-save handler ───────────────────────────────────────────────
  // Posts to BFF test-transient action without creating a DB record.
  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    setTestError(null);

    // Gather the credential value field
    const secretField = secretFields[0];
    const credentialValue = secretField ? (credFields[secretField.name] ?? "") : "";

    const payload = {
      service: {
        name: name.trim(),
        base_url: baseUrl.trim(),
        auth_scheme: authScheme,
      },
      credential: {
        value: credentialValue,
        header_name: credFields.header_name ?? undefined,
        query_param: credFields.param_name ?? undefined,
      },
      test: {
        method: "GET",
        path: testPath || "/health",
        timeout_ms: 5000,
      },
    };

    const api = new ApiClient();
    try {
      const resp = await api.resourceAction({
        resourceId: resource?.id ?? "services",
        actionName: "test-transient",
        method: "post",
        data: payload,
      });

      const data = resp.data as {
        testResult?: TestResult;
        record?: { params?: { testResult?: TestResult } };
      };
      const result =
        data?.testResult ??
        data?.record?.params?.testResult ??
        null;

      if (result) {
        setTestResult(result);
      } else {
        setTestError("Unexpected response — no test result returned");
      }
    } catch (err: unknown) {
      setTestError(err instanceof Error ? err.message : "Test request failed");
    } finally {
      setTesting(false);
    }
  };

  // ── is test button enabled? ─────────────────────────────────────────────────
  // Enabled when: name + base_url + auth_scheme populated AND a credential value field
  // exists AND it is populated. For "none" scheme (no cred), allow testing anyway.
  const secretField = secretFields[0];
  const credentialValue = secretField ? (credFields[secretField.name] ?? "") : "";
  const canTest =
    name.trim() !== "" &&
    baseUrl.trim() !== "" &&
    authScheme !== "" &&
    (secretField == null || credentialValue !== "");

  const handleSchemeChange = (newScheme: string) => {
    setAuthScheme(newScheme);
    setCredFields({}); // Reset cred fields when scheme changes
  };

  const setCredField = (fieldName: string, value: string) => {
    setCredFields((prev: Record<string, string>) => ({ ...prev, [fieldName]: value }));
  };

  // ── submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError("Service name is required."); return; }
    if (!baseUrl.trim()) { setError("Base URL is required."); return; }

    setSubmitting(true);
    setError(null);

    const api = new ApiClient();

    // Step 1: Create the service via AdminJS action handler
    let serviceId: string | undefined;
    try {
      const svcResp = await api.resourceAction({
        resourceId: resource?.id ?? "services",
        actionName: "new",
        method: "post",
        data: {
          name,
          base_url: baseUrl,
          auth_scheme: authScheme,
          description,
          openapi_url: openapiUrl,
        },
      });

      const svcResult = svcResp.data as {
        record?: { id?: string | number };
        redirectUrl?: string;
        notice?: { message: string; type: string };
      };

      if (svcResult?.notice?.type === "error") {
        setError(svcResult.notice.message || "Failed to create service.");
        return;
      }

      // Extract service ID from redirectUrl (/admin/resources/services/records/<id>/show)
      const redirect = svcResult?.redirectUrl ?? "";
      const idMatch = redirect.match(/records\/([^/]+)\/show/);
      serviceId = idMatch ? idMatch[1] : String(svcResult?.record?.id ?? "");

      if (!serviceId) {
        setError("Service created but could not determine its ID. Please refresh the list.");
        return;
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Service creation failed.");
      return;
    } finally {
      setSubmitting(false);
    }

    // Step 2 (optional): Create credential
    if (!addCredential || schemeFields.length === 0) {
      setSuccess({ serviceId, credentialCreated: false });
      return;
    }

    setSubmitting(true);
    let credentialWarning: string | undefined;
    try {
      const credPayload: Record<string, string> = {
        auth_scheme: authScheme,
        service_id: serviceId,
        ...credFields,
      };

      // Remove empty hint fields so admin-api doesn't receive empty strings
      // that the operator left blank (optional fields).
      for (const key of Object.keys(credPayload)) {
        if (credPayload[key] === "" && key !== "value") {
          delete credPayload[key];
        }
      }

      const credResp = await api.resourceAction({
        resourceId: "credentials",
        actionName: "new",
        method: "post",
        data: credPayload,
      });

      const credResult = credResp.data as {
        notice?: { message: string; type: string };
      };

      if (credResult?.notice?.type === "error") {
        credentialWarning = credResult.notice.message || "Credential creation failed — please add it manually.";
      }
    } catch (err: unknown) {
      credentialWarning = err instanceof Error
        ? `Credential creation failed: ${err.message} — service was created; add credential manually.`
        : "Credential creation failed — service was created; add credential manually.";
    } finally {
      setSubmitting(false);
    }

    setSuccess({ serviceId, credentialCreated: !credentialWarning, credentialWarning });
  };

  // ── success state ──────────────────────────────────────────────────────────
  if (success) {
    const showUrl = `/admin/resources/services/records/${success.serviceId}/show`;
    const testUrl = `/admin/resources/services/records/${success.serviceId}/testService`;

    return (
      <Box variant="white" p="xxl" data-testid="service-create-success">
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#d4edda",
            border: "1px solid #c3e6cb",
            borderRadius: 4,
          }}
          data-testid="success-banner"
        >
          <Text style={{ fontWeight: 600, color: "#155724" }}>
            Service registered successfully.
          </Text>
          {success.credentialCreated && (
            <Text style={{ color: "#155724", marginTop: 4 }}>
              Credential registered. You can now test the connection.
            </Text>
          )}
          {!success.credentialCreated && !success.credentialWarning && (
            <Text style={{ color: "#155724", marginTop: 4 }}>
              No credential was added. You can add one on the service page.
            </Text>
          )}
        </Box>

        {success.credentialWarning && (
          <Box
            mb="lg"
            p="lg"
            style={{
              background: "#fff3cd",
              border: "1px solid #ffc107",
              borderRadius: 4,
            }}
            data-testid="credential-warning"
          >
            <Text style={{ color: "#856404" }}>{success.credentialWarning}</Text>
          </Box>
        )}

        <Box flex style={{ gap: 12 }}>
          <Button
            as="a"
            href={testUrl}
            variant="primary"
            data-testid="test-connection-btn"
          >
            Test connection
          </Button>
          <Button
            as="a"
            href={showUrl}
            variant="light"
            data-testid="skip-to-service-btn"
          >
            View service
          </Button>
        </Box>
      </Box>
    );
  }

  // ── form ──────────────────────────────────────────────────────────────────
  return (
    <Box variant="white" p="xxl" data-testid="service-create-form">
      <H3 mb="lg">New Service</H3>

      {/* ── Template pre-fill banner ──────────────────────────────────── */}
      {templateName && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#cce5ff",
            border: "1px solid #b8daff",
            borderRadius: 4,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 8,
          }}
          data-testid="template-prefill-banner"
        >
          <Text style={{ color: "#004085" }}>
            Pre-filled from template: <strong>{templateName}</strong>.
          </Text>
          <Button
            as="a"
            href="/admin/resources/services/actions/new"
            variant="light"
            size="sm"
            data-testid="template-prefill-clear"
            onClick={() => {
              setName("");
              setBaseUrl("");
              setAuthScheme("none");
              setDescription("");
              setOpenapiUrl("");
              setTemplateName(null);
              setCredFields({});
              setTestPath("/health");
              navigate("/admin/resources/services/actions/new");
            }}
          >
            Clear
          </Button>
        </Box>
      )}

      <Text mb="xl" style={{ color: "#6c757d" }}>
        Register a backend API that Agents will call through the Mintkey egress proxy.
        Auth-scheme-specific fields are shown automatically below.
      </Text>

      <form onSubmit={handleSubmit} noValidate>
        {/* ── Standard service fields ──────────────────────────────────── */}
        <FieldRow id="name" label="Name" required>
          <Input
            id="name"
            value={name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
            placeholder="My API Service"
            style={inputStyle}
            required
            data-testid="field-input-name"
          />
        </FieldRow>

        <FieldRow id="base_url" label="Base URL" required>
          <Input
            id="base_url"
            type="url"
            value={baseUrl}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setBaseUrl(e.target.value)}
            placeholder="https://api.example.com"
            style={inputStyle}
            required
            data-testid="field-input-base_url"
          />
        </FieldRow>

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

        <FieldRow id="description" label="Description">
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
            style={textareaStyle}
            data-testid="field-input-description"
          />
        </FieldRow>

        <FieldRow id="openapi_url" label="OpenAPI URL">
          <Input
            id="openapi_url"
            type="url"
            value={openapiUrl}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpenapiUrl(e.target.value)}
            placeholder="https://api.example.com/openapi.json"
            style={inputStyle}
            data-testid="field-input-openapi_url"
          />
        </FieldRow>

        {/* ── Conditional auth-scheme hint fields ──────────────────────── */}
        {hintFields.length > 0 && (
          <Box
            mt="lg"
            mb="default"
            p="lg"
            style={{ background: "#f8f9fa", border: "1px solid #dee2e6", borderRadius: 4 }}
            data-testid="auth-scheme-hint-fields"
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

        {/* ── Optional inline credential section ───────────────────────── */}
        {schemeFields.length > 0 && (
          <Box mt="xl" mb="default" data-testid="add-credential-section">
            <Box
              mb="default"
              style={{ display: "flex", alignItems: "center", gap: 8 }}
            >
              <input
                type="checkbox"
                id="add_credential"
                checked={addCredential}
                onChange={(e) => setAddCredential(e.target.checked)}
                data-testid="add-credential-checkbox"
                style={{ width: 16, height: 16, cursor: "pointer" }}
              />
              <label
                htmlFor="add_credential"
                style={{ cursor: "pointer", fontSize: 14, fontWeight: 500 }}
              >
                Add a credential now?
              </label>
            </Box>
            <Text style={{ fontSize: 12, color: "#6c757d", marginTop: -4 }}>
              You can always add a credential later from the service page.
            </Text>

            {addCredential && (
              <Box
                mt="lg"
                p="lg"
                style={{
                  background: "#fff",
                  border: "1px solid #dee2e6",
                  borderRadius: 4,
                }}
                data-testid="credential-subform"
              >
                <Text mb="default" style={{ fontWeight: 600, color: "#495057" }}>
                  Credential details
                </Text>

                {/* Secret field(s) — e.g. the API key value */}
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
          </Box>
        )}

        {/* ── Test-before-save ─────────────────────────────────────────── */}
        <Box mt="xl" mb="default" data-testid="test-before-save-section">
          <FieldRow id="test_path" label="Test path">
            <Input
              id="test_path"
              value={testPath}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTestPath(e.target.value)}
              placeholder="/health"
              style={inputStyle}
              data-testid="field-input-test_path"
            />
            <Text style={{ fontSize: 12, color: "#6c757d", marginTop: 4 }}>
              Path appended to base URL for the connection test (e.g. <code>/user</code> for GitHub, <code>/health</code> for generic services).
            </Text>
          </FieldRow>
          <Button
            type="button"
            variant="secondary"
            disabled={!canTest || testing}
            onClick={handleTestConnection}
            data-testid="test-before-save-btn"
          >
            {testing ? "Testing…" : "Test connection"}
          </Button>
          {!canTest && (
            <Text style={{ fontSize: 12, color: "#6c757d", marginTop: 4 }}>
              Fill in name, base URL, auth scheme and credential value to enable.
            </Text>
          )}
        </Box>

        {/* ── Test error ──────────────────────────────────────────────── */}
        {testError && (
          <Box
            mb="lg"
            p="lg"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
            }}
            data-testid="test-before-save-error"
          >
            <Text style={{ color: "#721c24" }}>{testError}</Text>
          </Box>
        )}

        {/* ── Inline test result panel ─────────────────────────────────── */}
        {testResult !== null && (
          <Box mt="default" mb="lg" data-testid="test-before-save-result">
            <Box
              p="lg"
              style={{
                background: testResult.ok ? "#d4edda" : "#f8d7da",
                border: `1px solid ${testResult.ok ? "#c3e6cb" : "#f5c6cb"}`,
                borderRadius: 4,
                marginBottom: 8,
              }}
              data-testid="test-before-save-status"
            >
              <Text
                style={{
                  fontWeight: 700,
                  fontSize: 18,
                  color: testResult.ok ? "#155724" : "#721c24",
                }}
              >
                {testResult.ok ? "✓" : "✗"}{" "}
                {testResult.status_code != null
                  ? String(testResult.status_code)
                  : (testResult.error ?? "—")}
                {testResult.latency_ms != null && (
                  <span style={{ fontWeight: 400, fontSize: 13, marginLeft: 12 }}>
                    {testResult.latency_ms} ms
                  </span>
                )}
              </Text>
              {!testResult.ok && (
                <Text style={{ fontSize: 12, color: "#721c24", marginTop: 4 }}>
                  A failed test does not block saving. Fix the connection later or save now.
                </Text>
              )}
            </Box>

            {testResult.final_url && (
              <Box
                mb="default"
                p="default"
                style={{
                  background: "#f8f9fa",
                  border: "1px solid #dee2e6",
                  borderRadius: 4,
                  fontFamily: "monospace",
                  fontSize: 12,
                  wordBreak: "break-all",
                }}
                data-testid="test-before-save-final-url"
              >
                {testResult.final_url}
              </Box>
            )}

            {testResult.response_body_truncated != null && (
              <Box
                mb="default"
                p="default"
                style={{
                  background: "#f8f9fa",
                  border: "1px solid #dee2e6",
                  borderRadius: 4,
                  fontFamily: "monospace",
                  fontSize: 12,
                  maxHeight: 160,
                  overflowY: "auto",
                  wordBreak: "break-all",
                }}
                data-testid="test-before-save-body"
              >
                {testResult.response_body_truncated || "(empty response)"}
              </Box>
            )}
          </Box>
        )}

        {/* ── Error display ────────────────────────────────────────────── */}
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

        {/* ── Buttons ──────────────────────────────────────────────────── */}
        <Box flex mt="xl" style={{ gap: 12 }}>
          <Button
            type="submit"
            variant="primary"
            disabled={submitting}
            data-testid="service-create-submit"
          >
            {submitting ? "Creating…" : "Create Service"}
          </Button>
          <Button
            as="a"
            href={`/admin/resources/${resource?.id ?? "services"}`}
            variant="light"
            data-testid="service-create-cancel"
            onClick={() => navigate(`/admin/resources/${resource?.id ?? "services"}`)}
          >
            Cancel
          </Button>
        </Box>
      </form>
    </Box>
  );
};

export default ServiceCreateForm;
