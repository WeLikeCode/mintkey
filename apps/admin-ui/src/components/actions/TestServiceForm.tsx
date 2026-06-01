/**
 * TestServiceForm — custom action component for testService (UX-CLARITY P0).
 *
 * Replaces the generic ConfirmAction two-button page with a proper form that:
 *   1. Exposes all 5 TestRunRequest fields (method, path, headers, body, timeout_ms).
 *   2. Shows a live curl preview that updates as the operator types.
 *   3. Validates JSON headers inline (before submit).
 *   4. Calls the action handler via ApiClient.recordAction (option C — component
 *      drives the call; handler is a passthrough).
 *   5. Renders a rich result panel: ok, status_code, latency_ms, final_url,
 *      response_body_truncated.
 *
 * SSH services (auth_scheme ∈ {ssh_private_key, ssh_password, ssh_ca}):
 *   Method / Path / Headers / Body / curl preview are hidden — they are
 *   meaningless for an SSH dial.  The panel shows the target URL from base_url
 *   and a single Timeout field.  The SSH user comes from the vault credential
 *   metadata at test time; we don't fetch it here to avoid an extra round-trip
 *   (v1 simplicity — the test result message confirms the actual user used).
 *
 * Source: UX-CLARITY P0; ADMIN_UI_SPEC.md §1.4; ADR-0021.
 */

import React, { useState, useMemo } from "react";
import {
  Box,
  H3,
  H4,
  Text,
  Button,
  Label,
  Input,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";

// ── SSH schemes ───────────────────────────────────────────────────────────────

const SSH_AUTH_SCHEMES = new Set(["ssh_private_key", "ssh_password", "ssh_ca"]);

// ── types ────────────────────────────────────────────────────────────────────

// Props injected by AdminJS for record-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS";

interface TestResult {
  ok: boolean;
  status_code?: number;
  latency_ms?: number;
  final_url?: string;
  response_body_truncated?: string;
  error?: string;
}

// ── style constants ───────────────────────────────────────────────────────────

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

const monoBlock: React.CSSProperties = {
  background: "#1e1e2e",
  color: "#cdd6f4",
  borderRadius: 4,
  padding: "12px 16px",
  fontFamily: "monospace",
  fontSize: 13,
  lineHeight: "1.6",
  whiteSpace: "pre-wrap",
  wordBreak: "break-all",
  overflowX: "auto",
};

// ── helpers ───────────────────────────────────────────────────────────────────

const HTTP_METHODS: HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

function buildCurlPreview(
  method: HttpMethod,
  baseUrl: string,
  path: string,
  headersRaw: string,
  body: string
): string {
  const url = `${baseUrl.replace(/\/$/, "")}${path || "/"}`;
  const lines: string[] = [`curl -X ${method} "${url}"`];

  // Parse headers — we already validate them live, just skip if invalid
  let parsedHeaders: Record<string, string> = {};
  try {
    if (headersRaw.trim()) {
      parsedHeaders = JSON.parse(headersRaw) as Record<string, string>;
    }
  } catch {
    // invalid JSON — show placeholder
    parsedHeaders = {};
  }

  // Add Content-Type if not already present and there may be a body
  const hasExplicitCT = Object.keys(parsedHeaders).some(
    (k) => k.toLowerCase() === "content-type"
  );
  if (!hasExplicitCT && ["POST", "PUT", "PATCH"].includes(method)) {
    lines.push(`  -H "Content-Type: application/json"`);
  }

  for (const [k, v] of Object.entries(parsedHeaders)) {
    lines.push(`  -H "${k}: ${v}"`);
  }

  if (body.trim()) {
    const escaped = body.replace(/'/g, "'\\''");
    lines.push(`  -d '${escaped}'`);
  }

  return lines.join(" \\\n");
}

// ── FieldRow ─────────────────────────────────────────────────────────────────

interface FieldRowProps {
  id: string;
  label: string;
  required?: boolean;
  children: React.ReactNode;
}

const FieldRow = ({ id, label, required, children }: FieldRowProps): React.ReactElement => (
  <Box mb="default" data-testid={`field-${id}`}>
    <Label htmlFor={id} required={required}>{label}</Label>
    {children}
  </Box>
);

// ── ResultPanel ───────────────────────────────────────────────────────────────

interface ResultPanelProps {
  result: TestResult;
}

const ResultPanel = ({ result }: ResultPanelProps): React.ReactElement => {
  const isOk = result.ok;
  const statusIcon = isOk ? "✓" : "✗";
  const bannerStyle: React.CSSProperties = {
    background: isOk ? "#d4edda" : "#f8d7da",
    border: `1px solid ${isOk ? "#c3e6cb" : "#f5c6cb"}`,
    borderRadius: 4,
    padding: "16px 20px",
    marginBottom: 16,
  };
  const statusColor = isOk ? "#155724" : "#721c24";

  return (
    <Box mt="xl" data-testid="test-result-panel">
      <H4 mb="default">Result</H4>

      <div style={bannerStyle}>
        <Text style={{ fontWeight: 700, fontSize: 20, color: statusColor }}>
          {statusIcon}{" "}
          {result.status_code != null ? String(result.status_code) : (result.error ?? "—")}
          {result.latency_ms != null && (
            <span style={{ fontWeight: 400, fontSize: 14, marginLeft: 12 }}>
              {result.latency_ms} ms
            </span>
          )}
        </Text>
      </div>

      {result.final_url && (
        <Box mb="default" data-testid="result-final-url">
          <Label>Final URL</Label>
          <Box
            p="default"
            style={{
              background: "#f8f9fa",
              border: "1px solid #dee2e6",
              borderRadius: 4,
              fontFamily: "monospace",
              fontSize: 13,
              wordBreak: "break-all",
            }}
          >
            {result.final_url}
          </Box>
        </Box>
      )}

      {result.response_body_truncated != null && (
        <Box mb="default" data-testid="result-response-body">
          <Label>Response body (first 500 chars)</Label>
          <div
            style={{
              ...monoBlock,
              background: "#f8f9fa",
              color: "#212529",
              maxHeight: 240,
              overflowY: "auto",
              border: "1px solid #dee2e6",
            }}
          >
            {result.response_body_truncated || "(empty)"}
          </div>
        </Box>
      )}

      {result.error && !result.status_code && (
        <Box mb="default" data-testid="result-error">
          <Label>Error</Label>
          <Box
            p="default"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
              fontFamily: "monospace",
              fontSize: 13,
            }}
          >
            {result.error}
          </Box>
        </Box>
      )}
    </Box>
  );
};

// ── SSHTestPanel ─────────────────────────────────────────────────────────────

interface SSHTestPanelProps {
  baseUrl: string;
  recordId: string;
  resourceId: string;
  actionName: string;
  cancelHref: string;
}

const SSHTestPanel = ({
  baseUrl,
  recordId,
  resourceId,
  actionName,
  cancelHref,
}: SSHTestPanelProps): React.ReactElement => {
  const [timeoutMs, setTimeoutMs] = useState(10000);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResult | null>(null);

  // Show planned connection without exposing any credential.
  const sshCommand = `ssh <user>@${baseUrl.replace(/^ssh:\/\//, "")}`;

  const handleRun = async () => {
    setSubmitting(true);
    setSubmitError(null);
    setResult(null);

    try {
      const api = new ApiClient();
      const response = await api.recordAction({
        resourceId,
        recordId,
        actionName,
        method: "post",
        data: { timeout_ms: timeoutMs },
      });

      const data = response.data as {
        notice?: { message: string; type: string };
        testResult?: TestResult;
        record?: { params?: Record<string, unknown> };
      };

      const embedded =
        (data?.testResult as TestResult | undefined) ??
        (data?.record?.params?.testResult as TestResult | undefined);

      if (embedded) {
        setResult(embedded);
        return;
      }

      const noticeMsg = data?.notice?.message ?? "";
      if (noticeMsg) {
        try {
          const parsed = JSON.parse(noticeMsg) as TestResult;
          if (typeof parsed.ok === "boolean") {
            setResult(parsed);
            return;
          }
        } catch {
          // not JSON
        }
        const isErr = data?.notice?.type === "error";
        setResult({
          ok: !isErr,
          error: isErr ? noticeMsg : undefined,
          response_body_truncated: isErr ? undefined : noticeMsg,
        });
        return;
      }

      setSubmitError("Unexpected response from server — no result data");
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box variant="white" p="xxl" data-testid="ssh-test-panel">
      <H3 mb="default">Test SSH Connection</H3>
      <Text mb="xl" style={{ color: "#6c757d" }}>
        Verifies that the stored SSH credential can authenticate to{" "}
        <strong style={{ fontFamily: "monospace", fontSize: 13 }}>{baseUrl}</strong>.
        {" "}The SSH user and key are taken from the vault — no credential is
        exposed here.
      </Text>

      {/* Planned SSH command — shows target but never the credential */}
      <Box mb="xl" data-testid="ssh-command-preview">
        <Label>Planned connection</Label>
        <div style={monoBlock} data-testid="ssh-command-block">
          {sshCommand}
        </div>
      </Box>

      {/* Timeout */}
      <Box mb="xl">
        <Label htmlFor="ssh-timeout">Timeout (ms)</Label>
        <Input
          id="ssh-timeout"
          type="number"
          value={String(timeoutMs)}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
            setTimeoutMs(parseInt(e.target.value, 10) || 10000)
          }
          style={{ ...inputStyle, maxWidth: 200 }}
          data-testid="field-input-ssh-timeout"
        />
      </Box>

      {submitError && (
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            borderRadius: 4,
          }}
          data-testid="submit-error"
        >
          <Text style={{ color: "#721c24" }}>{submitError}</Text>
        </Box>
      )}

      <Box flex style={{ gap: 12 }}>
        <Button
          type="button"
          variant="primary"
          disabled={submitting}
          onClick={handleRun}
          data-testid="test-service-submit"
        >
          {submitting ? "Testing…" : "Run Test"}
        </Button>
        <Button
          as="a"
          href={cancelHref}
          variant="light"
          data-testid="test-service-cancel"
        >
          Cancel
        </Button>
      </Box>

      {result !== null && <ResultPanel result={result} />}
    </Box>
  );
};

// ── TestServiceForm (main component) ─────────────────────────────────────────

const TestServiceForm = (props: Props): React.ReactElement => {
  const { record, resource, action } = props as {
    record: {
      id: string | number;
      params: Record<string, unknown>;
    };
    resource: { id: string };
    action: { name: string; label: string };
  };

  // Extract base_url and auth_scheme from the service record if available
  const baseUrl =
    (record?.params?.base_url as string | undefined) ??
    "{base_url}";

  const authScheme =
    (record?.params?.auth_scheme as string | undefined) ?? "";

  const cancelHref = record?.id
    ? `/admin/resources/${resource.id}/records/${record.id}/show`
    : `/admin/resources/${resource.id}`;

  // SSH services: hide HTTP form fields entirely — they are meaningless for
  // an SSH dial. Show SSHTestPanel instead. Detected via auth_scheme field
  // (source of truth) which is always present on the service record params.
  if (SSH_AUTH_SCHEMES.has(authScheme)) {
    return (
      <SSHTestPanel
        baseUrl={baseUrl}
        recordId={String(record.id)}
        resourceId={resource.id}
        actionName={action.name}
        cancelHref={cancelHref}
      />
    );
  }

  // ── form state ────────────────────────────────────────────────────────────
  const [method, setMethod] = useState<HttpMethod>("GET");
  const [path, setPath] = useState("/health");
  const [headersRaw, setHeadersRaw] = useState("");
  const [body, setBody] = useState("");
  const [timeoutMs, setTimeoutMs] = useState(5000);

  // ── validation state ──────────────────────────────────────────────────────
  const [headersError, setHeadersError] = useState<string | null>(null);

  // ── submission state ──────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResult | null>(null);

  // ── live curl preview ─────────────────────────────────────────────────────
  const curlPreview = useMemo(
    () => buildCurlPreview(method, baseUrl, path, headersRaw, body),
    [method, baseUrl, path, headersRaw, body]
  );

  // ── handlers ──────────────────────────────────────────────────────────────

  const validateHeaders = (raw: string): boolean => {
    if (!raw.trim()) {
      setHeadersError(null);
      return true;
    }
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
        setHeadersError("Headers must be a JSON object, e.g. {\"X-Trace\": \"test\"}");
        return false;
      }
      setHeadersError(null);
      return true;
    } catch {
      setHeadersError("Invalid JSON — check for missing quotes or commas");
      return false;
    }
  };

  const handleHeadersChange = (raw: string) => {
    setHeadersRaw(raw);
    if (raw.trim()) {
      validateHeaders(raw);
    } else {
      setHeadersError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateHeaders(headersRaw)) {
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    setResult(null);

    let parsedHeaders: Record<string, string> | undefined;
    try {
      if (headersRaw.trim()) {
        parsedHeaders = JSON.parse(headersRaw) as Record<string, string>;
      }
    } catch {
      setSubmitError("Headers JSON is invalid");
      setSubmitting(false);
      return;
    }

    const payload: Record<string, unknown> = {
      method,
      path,
      timeout_ms: timeoutMs,
    };
    if (parsedHeaders) payload.headers = parsedHeaders;
    if (body.trim()) payload.body = body;

    try {
      const api = new ApiClient();
      const response = await api.recordAction({
        resourceId: resource.id,
        recordId: String(record.id),
        actionName: action.name,
        method: "post",
        data: payload,
      });

      const data = response.data as {
        notice?: { message: string; type: string };
        testResult?: TestResult;
        record?: { params?: Record<string, unknown> };
      };

      // Option C: the response embeds testResult in record.params.testResult
      // OR in a top-level testResult field, OR we parse the notice message
      const embedded =
        (data?.testResult as TestResult | undefined) ??
        (data?.record?.params?.testResult as TestResult | undefined);

      if (embedded) {
        setResult(embedded);
        return;
      }

      // Fallback: parse notice message (option A — if backend sends JSON notice)
      const noticeMsg = data?.notice?.message ?? "";
      if (noticeMsg) {
        try {
          const parsed = JSON.parse(noticeMsg) as TestResult;
          if (typeof parsed.ok === "boolean") {
            setResult(parsed);
            return;
          }
        } catch {
          // not JSON — show raw notice
        }
        // Raw notice message fallback — construct a basic result
        const isErr = data?.notice?.type === "error";
        setResult({
          ok: !isErr,
          error: isErr ? noticeMsg : undefined,
          status_code: undefined,
          latency_ms: undefined,
          final_url: undefined,
          response_body_truncated: isErr ? undefined : noticeMsg,
        });
        return;
      }

      setSubmitError("Unexpected response from server — no result data");
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box variant="white" p="xxl" data-testid="test-service-form">
      <H3 mb="default">Test Connection</H3>
      <Text mb="xl" style={{ color: "#6c757d" }}>
        Send a live test request to{" "}
        <strong style={{ fontFamily: "monospace", fontSize: 13 }}>
          {baseUrl}
        </strong>
        {" "}using the configured credentials. Verify connectivity before routing agents.
      </Text>

      <form onSubmit={handleSubmit} noValidate>
        {/* ── Method + Path row ────────────────────────────────────────── */}
        <Box
          mb="default"
          style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 12 }}
        >
          <Box data-testid="field-method">
            <Label htmlFor="test-method">Method</Label>
            <select
              id="test-method"
              value={method}
              onChange={(e) => setMethod(e.target.value as HttpMethod)}
              style={selectStyle}
              data-testid="field-select-method"
            >
              {HTTP_METHODS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </Box>

          <Box data-testid="field-path">
            <Label htmlFor="test-path">Path</Label>
            <Input
              id="test-path"
              value={path}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPath(e.target.value)}
              placeholder="/v1/api/endpoint"
              style={inputStyle}
              data-testid="field-input-path"
            />
          </Box>
        </Box>

        {/* ── Headers ─────────────────────────────────────────────────── */}
        <FieldRow id="headers" label="Headers (JSON, optional)">
          <textarea
            id="headers"
            value={headersRaw}
            onChange={(e) => handleHeadersChange(e.target.value)}
            placeholder='{"X-Trace": "test"}'
            style={{
              ...textareaStyle,
              borderColor: headersError ? "#dc3545" : "#dee2e6",
            }}
            data-testid="field-input-headers"
          />
          {headersError && (
            <Text
              style={{ color: "#dc3545", fontSize: 12, marginTop: 4 }}
              data-testid="headers-json-error"
            >
              {headersError}
            </Text>
          )}
        </FieldRow>

        {/* ── Body ────────────────────────────────────────────────────── */}
        <FieldRow id="body" label="Body (optional)">
          <textarea
            id="body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="request body if POST/PUT/PATCH"
            style={textareaStyle}
            data-testid="field-input-body"
          />
        </FieldRow>

        {/* ── Timeout ─────────────────────────────────────────────────── */}
        <FieldRow id="timeout_ms" label="Timeout (ms)">
          <Input
            id="timeout_ms"
            type="number"
            value={String(timeoutMs)}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              setTimeoutMs(parseInt(e.target.value, 10) || 5000)
            }
            style={{ ...inputStyle, maxWidth: 200 }}
            data-testid="field-input-timeout"
          />
        </FieldRow>

        {/* ── Live curl preview ────────────────────────────────────────── */}
        <Box mb="xl" data-testid="curl-preview-section">
          <Label>curl preview</Label>
          <div style={monoBlock} data-testid="curl-preview">
            {curlPreview}
          </div>
        </Box>

        {/* ── Submit error ─────────────────────────────────────────────── */}
        {submitError && (
          <Box
            mb="lg"
            p="lg"
            style={{
              background: "#f8d7da",
              border: "1px solid #f5c6cb",
              borderRadius: 4,
            }}
            data-testid="submit-error"
          >
            <Text style={{ color: "#721c24" }}>{submitError}</Text>
          </Box>
        )}

        {/* ── Buttons ─────────────────────────────────────────────────── */}
        <Box flex style={{ gap: 12 }}>
          <Button
            type="submit"
            variant="primary"
            disabled={submitting || !!headersError}
            data-testid="test-service-submit"
          >
            {submitting ? "Testing…" : "Run Test"}
          </Button>
          <Button
            as="a"
            href={cancelHref}
            variant="light"
            data-testid="test-service-cancel"
          >
            Cancel
          </Button>
        </Box>
      </form>

      {/* ── Result panel ───────────────────────────────────────────────── */}
      {result !== null && <ResultPanel result={result} />}
    </Box>
  );
};

export default TestServiceForm;
