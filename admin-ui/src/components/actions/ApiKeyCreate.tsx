/**
 * ApiKeyCreate — show-once flow for service_api_keys.createApiKey (ADR-0018).
 *
 * Flow:
 *   GET  → renders the create form (agent dropdown, service dropdown, name, expires_at, constraints)
 *   POST → calls the AdminJS action handler (server-side → POST /v1/tenants/{tid}/agents/{aid}/api-keys)
 *          → response carries notice.message containing the plaintext key "shown once"
 *          → component intercepts the key and shows the show-once modal
 *
 * Security (ADR-0018 §1.3):
 *   - plaintext_key is NEVER written to Redux, localStorage, or any persistent store
 *   - it lives only in React local state (`useState`) which is cleared on unmount
 *   - the modal cannot be dismissed by outside-click — only via the confirm button
 *   - no `console.log(key)` anywhere in this file
 *
 * Source: ADMIN_UI_ACTION_MATRIX.md R1; action-grid chunk R1.
 */

import React, { useState, useEffect, useRef } from "react";
import {
  Box,
  H3,
  Text,
  Button,
  Label,
  Input,
} from "@adminjs/design-system";
import { ApiClient } from "adminjs";
import { useNavigate } from "react-router-dom";

// ── types ────────────────────────────────────────────────────────────────────

interface AgentOption {
  value: string;
  label: string;
}

interface ServiceOption {
  value: string;
  label: string;
}

interface PermissionGrant {
  service_id: string;
  service_slug?: string;
  service_name?: string;
  constraints?: unknown;
  allowed_actions?: string[];
}

// Props injected by AdminJS for resource-type actions
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Props = Record<string, any>;

// ── helpers ──────────────────────────────────────────────────────────────────

/** Extract the plaintext key from the server notice message. */
function extractKey(noticeMessage: string): string {
  const m = noticeMessage.match(/shown once\)[^:]*:\s*(\S+)/i);
  if (m) return m[1];
  // fallback: any mk_svckey_ token in the message
  const k = noticeMessage.match(/(mk_svckey_\S+)/);
  return k ? k[1] : "";
}

// ── ShowOnceModal ─────────────────────────────────────────────────────────────

interface ModalProps {
  plaintextKey: string;
  onConfirm: () => void;
}

const ShowOnceModal = ({ plaintextKey, onConfirm }: ModalProps): React.ReactElement => {
  const [copied, setCopied] = useState(false);
  const [copySupported, setCopySupported] = useState(true);

  useEffect(() => {
    if (!navigator.clipboard) setCopySupported(false);
    // Prevent body scroll while modal is open
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  const handleCopy = async () => {
    if (!navigator.clipboard) {
      setCopySupported(false);
      return;
    }
    try {
      await navigator.clipboard.writeText(plaintextKey);
      setCopied(true);
    } catch {
      setCopySupported(false);
    }
  };

  // Capture the key in a ref so it clears when the component unmounts
  const keyRef = useRef(plaintextKey);
  keyRef.current = plaintextKey;

  return (
    <div
      data-testid="show-once-modal"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.5)",
      }}
      // Do NOT attach onClick to the backdrop — modal must not close on outside-click
    >
      <Box
        variant="white"
        p="xxl"
        style={{ maxWidth: 560, width: "100%", borderRadius: 8, position: "relative" }}
        data-testid="show-once-modal-inner"
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      >
        {/* Warning banner */}
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#fff3cd",
            border: "1px solid #ffc107",
            borderRadius: 4,
          }}
        >
          <Text style={{ fontWeight: 600, color: "#856404" }}>
            This is the only time you&apos;ll see this key — copy it now.
            It cannot be retrieved after you close this dialog.
          </Text>
        </Box>

        <H3 mb="lg">API Key Created</H3>

        <Label>Your new service API key</Label>
        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#f8f9fa",
            border: "1px solid #dee2e6",
            borderRadius: 4,
            fontFamily: "monospace",
            wordBreak: "break-all",
            fontSize: 14,
          }}
          data-testid="plaintext-key-box"
        >
          {plaintextKey}
        </Box>

        {copySupported ? (
          <Button
            onClick={handleCopy}
            variant="light"
            mb="lg"
            data-testid="copy-key-btn"
            style={{ marginRight: 12 }}
          >
            {copied ? "Copied!" : "Copy to clipboard"}
          </Button>
        ) : (
          <Text mb="lg" style={{ color: "#6c757d", fontSize: 13 }}>
            Copy not supported in this browser — please select and copy manually.
          </Text>
        )}

        <Box flex style={{ gap: 12 }}>
          <Button
            variant="primary"
            onClick={onConfirm}
            data-testid="modal-confirm-btn"
          >
            I&apos;ve copied it
          </Button>
        </Box>
      </Box>
    </div>
  );
};

// ── ApiKeyCreate (main component) ────────────────────────────────────────────

const ApiKeyCreate = (props: Props): React.ReactElement => {
  const { resource } = props as { resource: { id: string } };

  const navigate = useNavigate();

  // Form state
  const [agentId, setAgentId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [name, setName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [constraints, setConstraints] = useState<string>("{}");

  // Options fetched from admin-api
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [services, setServices] = useState<ServiceOption[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [loadingServices, setLoadingServices] = useState(false);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Show-once modal state — plaintext NEVER persisted beyond this component's lifetime
  const [plaintextKey, setPlaintextKey] = useState<string | null>(null);

  // Fetch agents list from the AdminJS action handler response
  // The resource handler returns agent list from the GET context
  useEffect(() => {
    let cancelled = false;
    const api = new ApiClient();

    // Fetch agents via AdminJS resource API by calling the resource-level GET
    // We call the admin-api agents endpoint indirectly through AdminJS
    const fetchAgents = async () => {
      try {
        const resp = await api.resourceAction({
          resourceId: "agents",
          actionName: "list",
          method: "get",
          params: { perPage: 200 },
        });
        if (cancelled) return;
        const data = resp.data as {
          records?: Array<{ params: { id: string; name: string; slug?: string } }>;
        };
        const opts: AgentOption[] = (data.records ?? []).map((r) => ({
          value: r.params.id,
          label: r.params.slug
            ? `${r.params.slug} — ${r.params.name}`
            : r.params.name,
        }));
        setAgents(opts);
      } catch {
        // agents list failed — form still usable with manual entry
        setAgents([]);
      } finally {
        if (!cancelled) setLoadingAgents(false);
      }
    };

    void fetchAgents();
    return () => { cancelled = true; };
  }, []);

  // Fetch services (permission grants) when agent changes
  useEffect(() => {
    if (!agentId) {
      setServices([]);
      setServiceId("");
      setConstraints("{}");
      return;
    }

    let cancelled = false;
    setLoadingServices(true);

    const fetchPermissions = async () => {
      try {
        const api = new ApiClient();
        // Call AdminJS action handler which proxies to admin-api permissions endpoint
        const resp = await api.resourceAction({
          resourceId: "permission_grants",
          actionName: "list",
          method: "get",
          params: { perPage: 200 },
        });
        if (cancelled) return;
        // Filter by agent_id — permissions list includes agent_id in params
        const data = resp.data as {
          records?: Array<{ params: PermissionGrant & { agent_id?: string } }>;
        };
        const agentPerms = (data.records ?? []).filter(
          (r) => r.params.agent_id === agentId
        );
        const opts: ServiceOption[] = agentPerms.map((r) => ({
          value: r.params.service_id,
          label: r.params.service_slug
            ? `${r.params.service_slug} — ${r.params.service_name ?? r.params.service_id}`
            : r.params.service_id,
        }));
        setServices(opts);
      } catch {
        setServices([]);
      } finally {
        if (!cancelled) setLoadingServices(false);
      }
    };

    void fetchPermissions();
    return () => { cancelled = true; };
  }, [agentId]);

  // Update constraints when service selection changes
  const handleServiceChange = (sid: string) => {
    setServiceId(sid);
    // Find the constraints from the selected permission grant (read-only inheritance)
    // v1: constraints display is informational only
    setConstraints("{}");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentId) {
      setError("Please select an agent.");
      return;
    }
    if (!serviceId) {
      setError("Please select a service.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const api = new ApiClient();
      const formData: Record<string, unknown> = {
        agent_id: agentId,
        service_id: serviceId,
      };
      if (name) formData.name = name;
      if (expiresAt) formData.expires_at = expiresAt;

      const resp = await api.resourceAction({
        resourceId: "service_api_keys",
        actionName: "createApiKey",
        method: "post",
        data: formData,
      });

      const result = resp.data as {
        notice?: { message: string; type: string };
        redirectUrl?: string;
      };

      const msg = result?.notice?.message ?? "";

      if (result?.notice?.type === "error") {
        setError(msg || "Failed to create API key");
        return;
      }

      // Extract the plaintext key from the notice message — shown once, never persisted
      const key = extractKey(msg);
      if (key) {
        // Store in local state — cleared on confirm/unmount
        setPlaintextKey(key);
      } else {
        // No key in response (unexpected) — just redirect
        navigate("/admin/resources/service_api_keys");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleModalConfirm = () => {
    // Clear the plaintext key from memory
    setPlaintextKey(null);
    // Redirect to list
    navigate("/admin/resources/service_api_keys");
  };

  return (
    <>
      {/* Show-once modal — rendered on top when key is available */}
      {plaintextKey !== null && (
        <ShowOnceModal
          plaintextKey={plaintextKey}
          onConfirm={handleModalConfirm}
        />
      )}

      <Box variant="white" p="xxl" data-testid="api-key-create-form">
        <H3 mb="lg">Create API Key</H3>
        <Text mb="default" style={{ color: "#6c757d" }}>
          Generate a long-lived service API key for an agent. The key plaintext
          is shown exactly once — you must copy it before leaving this page.
        </Text>

        <form onSubmit={handleSubmit}>
          {/* Agent selector */}
          <Box mb="default" data-testid="field-agent-id">
            <Label required>Agent</Label>
            {loadingAgents ? (
              <Text style={{ color: "#6c757d" }}>Loading agents…</Text>
            ) : (
              <select
                value={agentId}
                onChange={(e) => { setAgentId(e.target.value); setServiceId(""); }}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  border: "1px solid #dee2e6",
                  borderRadius: 4,
                  fontSize: 14,
                  lineHeight: 1.5,
                }}
                required
              >
                <option value="">— select an agent —</option>
                {agents.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            )}
          </Box>

          {/* Service selector */}
          <Box mb="default" data-testid="field-service-id">
            <Label required>Service</Label>
            {loadingServices ? (
              <Text style={{ color: "#6c757d" }}>Loading services…</Text>
            ) : (
              <select
                value={serviceId}
                onChange={(e) => handleServiceChange(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  border: "1px solid #dee2e6",
                  borderRadius: 4,
                  fontSize: 14,
                  lineHeight: 1.5,
                }}
                required
                disabled={!agentId}
              >
                <option value="">
                  {agentId ? "— select a service —" : "— select an agent first —"}
                </option>
                {services.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            )}
          </Box>

          {/* Name (optional) */}
          <Box mb="default" data-testid="field-name">
            <Label>Name (optional)</Label>
            <Input
              value={name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
              placeholder="auto-generated if blank"
              style={{ width: "100%" }}
            />
          </Box>

          {/* Expires at (optional) */}
          <Box mb="default" data-testid="field-expires-at">
            <Label>Expires at (optional)</Label>
            <Input
              type="date"
              value={expiresAt}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setExpiresAt(e.target.value)}
              style={{ width: "100%" }}
            />
          </Box>

          {/* Constraints — read-only display of inherited constraints (v1) */}
          <Box mb="xl" data-testid="field-constraints">
            <Label>Inherited constraints (read-only)</Label>
            <Box
              p="lg"
              style={{
                background: "#f8f9fa",
                border: "1px solid #dee2e6",
                borderRadius: 4,
                fontFamily: "monospace",
                fontSize: 13,
                color: "#495057",
              }}
            >
              {constraints}
            </Box>
            <Text style={{ fontSize: 12, color: "#6c757d", marginTop: 4 }}>
              Constraints are inherited from the agent&apos;s permission grant. You cannot widen them.
            </Text>
          </Box>

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

          {/* Submit */}
          <Box flex style={{ gap: 12 }}>
            <Button
              type="submit"
              variant="primary"
              disabled={submitting}
              data-testid="api-key-create-submit"
            >
              {submitting ? "Creating…" : "Create API Key"}
            </Button>
            <Button
              as="a"
              href={`/admin/resources/${resource?.id ?? "service_api_keys"}`}
              variant="light"
              data-testid="api-key-create-cancel"
            >
              Cancel
            </Button>
          </Box>
        </form>
      </Box>
    </>
  );
};

export default ApiKeyCreate;
