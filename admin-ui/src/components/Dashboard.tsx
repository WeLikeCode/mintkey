/**
 * Mintkey custom dashboard component — replaces the stock AdminJS
 * "Welcome on Board!" tips screen.
 *
 * Renders:
 * 1. Data-model SVG diagram — visual entity-relationship overview.
 * 2. 6-step static onboarding flow ("Get started") with CTA links.
 * 3. Quick-start checklist (data-driven done/not-done items).
 * 4. At-a-glance counts.
 * 5. MCP onboarding modal — opened by the "Connect your LLM via MCP" CTA in
 *    both the onboarding flow and the quick-start checklist (UI-MCP-modal chunk).
 *
 * Imports of `react`, `@adminjs/design-system` and `adminjs` are treated as
 * externals by AdminJS's component bundler (AssetBundler.DEFAULT_EXTERNALS) —
 * they resolve to the `React` / `AdminJSDesignSystem` / `AdminJS` globals the
 * AdminJS frontend already ships, so this component adds no new dependency.
 *
 * Source: ADMIN_UI_SPEC.md §2.1; ADR-0019; admin-ui-ux-uplift chunk; UI-MCP-modal chunk.
 */

import React, { useEffect, useState } from "react";
import { Box, H2, H3, H4, H5, Text, Badge, Button, Illustration } from "@adminjs/design-system";
import { ApiClient } from "adminjs";

interface Checklist {
  hasServices: boolean;
  hasCredentials: boolean;
  hasAgents: boolean;
  hasPermissions: boolean;
  hasTested: boolean;
}

interface DashboardData {
  email: string;
  tenantId: string;
  servicesCount: number;
  agentsCount: number;
  permissionsCount: number;
  auditCount24h: number;
  checklist: Checklist;
}

interface Step {
  key: keyof Checklist;
  title: string;
  ctaLabel: string;
  ctaHref: string;
}

// ── MCP config modal ─────────────────────────────────────────────────────────

/**
 * The mcp.config.json snippet that operators copy into Claude Desktop / Claude
 * Code / any MCP client.  The transport is HTTP-SSE (streamable-http) because
 * the Mintkey MCP server exposes a FastAPI HTTP endpoint, not a local process.
 *
 * URL hierarchy (swap in order of specificity):
 *   1. Your production domain  →  https://mintkey.example.com/v1
 *   2. Your docker-compose dev →  http://localhost:8082/v1
 *
 * The bootstrap tool (/v1/tools/bootstrap) is unauthenticated — no credentials
 * or headers are required in this config.
 *
 * Source: UI-MCP-modal chunk; mcp-server port 8082 (docker-compose.yml #6).
 */
const MCP_CONFIG_SNIPPET = JSON.stringify(
  {
    mcpServers: {
      mintkey: {
        type: "http",
        url: "http://localhost:8082/v1",
        description:
          "Mintkey credential broker — call mintkey_bootstrap first (no auth required)",
      },
    },
  },
  null,
  2,
);

const McpConfigModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [copied, setCopied] = useState(false);
  const [copySupported, setCopySupported] = useState(true);

  useEffect(() => {
    if (!navigator.clipboard) setCopySupported(false);
    document.body.style.overflow = "hidden";

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const handleCopy = async () => {
    if (!navigator.clipboard) {
      setCopySupported(false);
      return;
    }
    try {
      await navigator.clipboard.writeText(MCP_CONFIG_SNIPPET);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      setCopySupported(false);
    }
  };

  return (
    <div
      data-testid="mcp-config-modal"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.5)",
      }}
      onClick={onClose}
    >
      <Box
        variant="white"
        p="xxl"
        style={{ maxWidth: 600, width: "100%", borderRadius: 8, position: "relative" }}
        data-testid="mcp-config-modal-inner"
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      >
        <H3 mb="default">Connect your LLM via MCP</H3>

        <Text mb="lg">
          Add this snippet to your MCP client config (e.g.{" "}
          <code>~/.claude/mcp.json</code> for Claude Desktop, or{" "}
          <code>.mcp.json</code> in your project for Claude Code) to let your AI
          agents bootstrap into Mintkey. The{" "}
          <code>mintkey_bootstrap</code> tool is unauthenticated — call it first
          and it will tell your agent how to authenticate and discover services.
          Replace{" "}
          <code>http://localhost:8082</code> with your production Mintkey URL
          (e.g. <code>https://mintkey.example.com</code>) before deploying.
        </Text>

        <Box
          mb="lg"
          p="lg"
          style={{
            background: "#f8f9fa",
            border: "1px solid #dee2e6",
            borderRadius: 4,
            fontFamily: "monospace",
            fontSize: 13,
            whiteSpace: "pre",
            overflowX: "auto",
            color: "#212529",
          }}
          data-testid="mcp-config-snippet"
        >
          {MCP_CONFIG_SNIPPET}
        </Box>

        <Box flex style={{ gap: 12 }}>
          {copySupported ? (
            <Button
              onClick={handleCopy}
              variant="primary"
              data-testid="mcp-config-copy-btn"
            >
              {copied ? "Copied!" : "Copy"}
            </Button>
          ) : (
            <Text style={{ color: "#6c757d", fontSize: 13, alignSelf: "center" }}>
              Select and copy the snippet above manually.
            </Text>
          )}
          <Button
            onClick={onClose}
            variant="light"
            data-testid="mcp-config-close-btn"
          >
            Close
          </Button>
        </Box>
      </Box>
    </div>
  );
};

// ── Dashboard data / steps ────────────────────────────────────────────────────

const STEPS: Step[] = [
  { key: "hasServices", title: "Register a backend service", ctaLabel: "Register a service", ctaHref: "/admin/resources/services/actions/new" },
  { key: "hasCredentials", title: "Add its credential and test it", ctaLabel: "Configure credentials", ctaHref: "/admin/resources/services" },
  { key: "hasAgents", title: "Create an agent", ctaLabel: "Create an agent", ctaHref: "/admin/resources/agents/actions/new" },
  { key: "hasPermissions", title: "Grant the agent a permission", ctaLabel: "Grant a permission", ctaHref: "/admin/resources/permission_grants/actions/new" },
  { key: "hasTested", title: "Connect your LLM to MCP", ctaLabel: "Show MCP config", ctaHref: "/admin/resources/agents" },
];

/** 6-step static onboarding flow (admin-ui-ux-uplift chunk). */
const ONBOARDING_STEPS = [
  { n: 1, label: "Register a Service", href: "/admin/resources/services", resource: "services" },
  { n: 2, label: "Attach a Credential", href: "/admin/resources/credentials", resource: "credentials" },
  { n: 3, label: "Create an Agent", href: "/admin/resources/agents", resource: "agents" },
  { n: 4, label: "Grant the Agent a Permission on the Service", href: "/admin/resources/permission_grants", resource: "permission_grants" },
  { n: 5, label: "(Optional) Issue a Service API Key for non-agent clients", href: "/admin/resources/service_api_keys", resource: "service_api_keys" },
  { n: 6, label: "Connect your LLM via MCP", href: "/admin/resources/agents", resource: "agents" },
];

/** Inline SVG data-model diagram — no extra libraries. */
const DataModelDiagram: React.FC = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 760 320"
    width="100%"
    style={{ maxWidth: 760, display: "block", fontFamily: "inherit" }}
    role="img"
    aria-label="Mintkey data-model diagram showing entity relationships"
    data-testid="data-model-diagram"
  >
    {/* ── Tenant box ──────────────────────────────────────── */}
    <rect x="10" y="120" width="120" height="44" rx="6" fill="#e8f4f8" stroke="#3795BE" strokeWidth="2" />
    <text x="70" y="147" textAnchor="middle" fontSize="13" fontWeight="bold" fill="#1a3c5e">Tenant</text>

    {/* ── Service box ─────────────────────────────────────── */}
    <rect x="200" y="60" width="120" height="44" rx="6" fill="#e8f0fb" stroke="#4a7ab5" strokeWidth="2" />
    <text x="260" y="87" textAnchor="middle" fontSize="13" fontWeight="bold" fill="#1a2d5a">Service</text>

    {/* ── Credential box ──────────────────────────────────── */}
    <rect x="200" y="180" width="120" height="44" rx="6" fill="#fef9e7" stroke="#d4ac0d" strokeWidth="2" />
    <text x="260" y="207" textAnchor="middle" fontSize="13" fontWeight="bold" fill="#5c4a00">Credential</text>

    {/* ── Agent box ───────────────────────────────────────── */}
    <rect x="200" y="120" width="120" height="44" rx="6" fill="#eafaf1" stroke="#27ae60" strokeWidth="2" />
    <text x="260" y="147" textAnchor="middle" fontSize="13" fontWeight="bold" fill="#1a5c33">Agent</text>

    {/* ── Permission Grant box ────────────────────────────── */}
    <rect x="400" y="90" width="140" height="44" rx="6" fill="#fdf2fb" stroke="#8e44ad" strokeWidth="2" />
    <text x="470" y="112" textAnchor="middle" fontSize="12" fontWeight="bold" fill="#5b2c6f">Permission</text>
    <text x="470" y="126" textAnchor="middle" fontSize="12" fontWeight="bold" fill="#5b2c6f">Grant</text>

    {/* ── Service API Key box ─────────────────────────────── */}
    <rect x="400" y="175" width="140" height="44" rx="6" fill="#fef5e4" stroke="#e67e22" strokeWidth="2" />
    <text x="470" y="197" textAnchor="middle" fontSize="12" fontWeight="bold" fill="#784212">Service API</text>
    <text x="470" y="211" textAnchor="middle" fontSize="12" fontWeight="bold" fill="#784212">Key (optional)</text>

    {/* ── Audit Events band ───────────────────────────────── */}
    <rect x="600" y="60" width="148" height="200" rx="6" fill="#fdfefe" stroke="#717d7e" strokeWidth="2" strokeDasharray="6,3" />
    <text x="674" y="88" textAnchor="middle" fontSize="11" fill="#4d5656" fontWeight="bold">Audit Events</text>
    <text x="674" y="106" textAnchor="middle" fontSize="10" fill="#717d7e">(cross-cutting,</text>
    <text x="674" y="120" textAnchor="middle" fontSize="10" fill="#717d7e">hash-chained)</text>
    <line x1="674" y1="128" x2="674" y2="238" stroke="#aab7b8" strokeWidth="1" strokeDasharray="3,3" />
    <text x="674" y="255" textAnchor="middle" fontSize="10" fill="#717d7e">all entities</text>
    <text x="674" y="268" textAnchor="middle" fontSize="10" fill="#717d7e">emit events</text>

    {/* ── Edges ───────────────────────────────────────────── */}
    {/* Tenant → Service */}
    <line x1="130" y1="132" x2="200" y2="95" stroke="#3795BE" strokeWidth="1.5" markerEnd="url(#arr)" />
    {/* Tenant → Agent */}
    <line x1="130" y1="142" x2="200" y2="142" stroke="#3795BE" strokeWidth="1.5" markerEnd="url(#arr)" />
    {/* Tenant → Credential (via Service) */}
    <line x1="130" y1="152" x2="200" y2="192" stroke="#3795BE" strokeWidth="1.5" markerEnd="url(#arr)" />
    {/* Service ↔ Credential (bidirectional — paired) */}
    <line x1="260" y1="104" x2="260" y2="180" stroke="#d4ac0d" strokeWidth="1.5" strokeDasharray="5,3" markerEnd="url(#arrGold)" markerStart="url(#arrGoldR)" />
    {/* Agent + Service → Permission Grant */}
    <line x1="320" y1="130" x2="400" y2="110" stroke="#8e44ad" strokeWidth="1.5" markerEnd="url(#arrPurple)" />
    <line x1="320" y1="90" x2="400" y2="107" stroke="#8e44ad" strokeWidth="1.5" markerEnd="url(#arrPurple)" />
    {/* Permission Grant → Service API Key (subset) */}
    <line x1="470" y1="134" x2="470" y2="175" stroke="#e67e22" strokeWidth="1.5" strokeDasharray="5,3" markerEnd="url(#arrOrange)" />
    {/* All → Audit (dashed arrows) */}
    <line x1="600" y1="155" x2="548" y2="155" stroke="#aab7b8" strokeWidth="1" strokeDasharray="4,2" markerEnd="url(#arrGrey)" />

    {/* ── Arrow markers ───────────────────────────────────── */}
    <defs>
      <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#3795BE" />
      </marker>
      <marker id="arrGold" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#d4ac0d" />
      </marker>
      <marker id="arrGoldR" markerWidth="8" markerHeight="8" refX="2" refY="3" orient="auto-start-reverse">
        <path d="M0,0 L0,6 L8,3 z" fill="#d4ac0d" />
      </marker>
      <marker id="arrPurple" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#8e44ad" />
      </marker>
      <marker id="arrOrange" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#e67e22" />
      </marker>
      <marker id="arrGrey" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#aab7b8" />
      </marker>
    </defs>

    {/* ── Legend ──────────────────────────────────────────── */}
    <text x="10" y="300" fontSize="10" fill="#555">Solid arrows = ownership/containment</text>
    <text x="10" y="313" fontSize="10" fill="#555">Dashed arrows = optional / cross-cutting link</text>
  </svg>
);

/** 6-step onboarding cards */
const OnboardingStep: React.FC<{
  n: number;
  label: string;
  href: string;
  resource: string;
  onMcpClick?: () => void;
}> = ({ n, label, href, resource, onMcpClick }) => (
  <Box
    flex
    alignItems="center"
    mb="lg"
    p="lg"
    style={{ border: "1px solid #d0e4ef", borderRadius: 6, background: "#f8fbfd" }}
    data-testid={`onboarding-step-${n}`}
  >
    <Box
      mr="lg"
      style={{
        width: 32, height: 32, borderRadius: "50%",
        background: "#3795BE", color: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontWeight: "bold", fontSize: 14, flexShrink: 0,
      }}
    >
      {n}
    </Box>
    <Box flexGrow={1}>
      <Text style={{ margin: 0 }}>{label}</Text>
    </Box>
    {onMcpClick ? (
      <Button
        onClick={onMcpClick}
        size="sm"
        variant="light"
        data-resource={resource}
        data-testid="mcp-connect-cta"
      >
        Show MCP config
      </Button>
    ) : (
      <Button as="a" href={href} size="sm" variant="light" data-resource={resource}>
        Open {label.replace(/^\(Optional\) /, "").split(" ").slice(0, 3).join(" ")}
      </Button>
    )}
  </Box>
);

const ChecklistItem: React.FC<{
  done: boolean;
  title: string;
  ctaLabel: string;
  ctaHref: string;
  onMcpClick?: () => void;
}> = ({ done, title, ctaLabel, ctaHref, onMcpClick }) => (
  <Box flex alignItems="center" mb="lg" data-testid="dashboard-checklist-item">
    <Box mr="lg" style={{ fontSize: 22, lineHeight: "22px" }}>{done ? "☑" : "☐"}</Box>
    <Box flexGrow={1}>
      <Text fontWeight="bold">{title}</Text>
    </Box>
    {done ? (
      <Badge variant="success">done</Badge>
    ) : onMcpClick ? (
      <Button
        onClick={onMcpClick}
        size="sm"
        variant="primary"
        data-testid="mcp-connect-cta"
      >
        {ctaLabel}
      </Button>
    ) : (
      <Button as="a" href={ctaHref} size="sm" variant="primary">{ctaLabel}</Button>
    )}
  </Box>
);

const Dashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [mcpModalOpen, setMcpModalOpen] = useState(false);

  useEffect(() => {
    const api = new ApiClient();
    api
      .getDashboard()
      .then((res: { data: DashboardData }) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoaded(true));
  }, []);

  const checklist: Checklist = data?.checklist ?? {
    hasServices: false, hasCredentials: false, hasAgents: false, hasPermissions: false, hasTested: false,
  };
  const nothingExists =
    loaded && !checklist.hasServices && !checklist.hasAgents && !checklist.hasPermissions &&
    (data?.servicesCount ?? 0) === 0 && (data?.agentsCount ?? 0) === 0;

  return (
    <>
      {/* ── MCP config modal ─────────────────────────────── */}
      {mcpModalOpen && <McpConfigModal onClose={() => setMcpModalOpen(false)} />}

    <Box variant="grey">
      <Box variant="white" mb="xxl">
        <H2>Mintkey — credential broker for AI agents</H2>
        <Text>
          Operator <strong>{data?.email || "—"}</strong>
          {data?.tenantId ? <> &middot; tenant <strong>{data.tenantId}</strong></> : null}
        </Text>
      </Box>

      {/* ── Data-model diagram ──────────────────────────── */}
      <Box variant="white" mb="xxl" data-testid="diagram-section">
        <H4 mb="lg">Data model</H4>
        <DataModelDiagram />
      </Box>

      {/* ── 6-step onboarding flow ──────────────────────── */}
      <Box variant="white" mb="xxl" data-testid="get-started-section">
        <H4 mb="lg">Get started</H4>
        {ONBOARDING_STEPS.map((s) => (
          <OnboardingStep
            key={s.n}
            n={s.n}
            label={s.label}
            href={s.href}
            resource={s.resource}
            onMcpClick={s.n === 6 ? () => setMcpModalOpen(true) : undefined}
          />
        ))}
      </Box>

      {nothingExists ? (
        <Box variant="white">
          <Box flex flexDirection="column" alignItems="center" py="xxl">
            <Illustration variant="Astronaut" width={120} height={120} />
            <H4 mt="lg">Register your first backend service</H4>
            <Text textAlign="center" mt="default" style={{ maxWidth: 560 }}>
              Mintkey brokers credentials between your AI agents and backend services. Register a
              service, attach its credential, create an agent, grant it access — your agent then
              discovers the service over MCP and calls it without ever seeing the real credential.
            </Text>
            <Box mt="xxl">
              <Button as="a" href="/admin/resources/services/actions/new" variant="primary" size="lg">
                Register your first backend service
              </Button>
            </Box>
          </Box>
        </Box>
      ) : (
        <>
          <Box variant="white" mb="xxl">
            <H4 mb="lg">Quick start</H4>
            {STEPS.map((s) => (
              <ChecklistItem
                key={s.key}
                done={checklist[s.key]}
                title={s.title}
                ctaLabel={s.ctaLabel}
                ctaHref={s.ctaHref}
                onMcpClick={s.key === "hasTested" ? () => setMcpModalOpen(true) : undefined}
              />
            ))}
          </Box>

          <Box variant="white">
            <H4 mb="lg">At a glance</H4>
            <Box flex flexWrap="wrap" style={{ gap: 24 }}>
              <Box data-testid="dashboard-count">
                <H5>{data?.servicesCount ?? 0}</H5>
                <Text variant="sm">services</Text>
              </Box>
              <Box data-testid="dashboard-count">
                <H5>{data?.agentsCount ?? 0}</H5>
                <Text variant="sm">agents</Text>
              </Box>
              <Box data-testid="dashboard-count">
                <H5>{data?.permissionsCount ?? 0}</H5>
                <Text variant="sm">active permissions</Text>
              </Box>
              <Box data-testid="dashboard-count">
                <H5>{data?.auditCount24h ?? 0}</H5>
                <Text variant="sm">audit events</Text>
              </Box>
            </Box>
          </Box>
        </>
      )}
    </Box>
    </>
  );
};

export default Dashboard;
