/**
 * Mintkey custom dashboard component — replaces the stock AdminJS
 * "Welcome on Board!" tips screen.
 *
 * Renders the quick-start onboarding checklist + at-a-glance counts + an empty
 * state, from the data produced by `dashboardHandler` (src/dashboard.ts), which
 * AdminJS exposes via `ApiClient#getDashboard()`.
 *
 * Imports of `react`, `@adminjs/design-system` and `adminjs` are treated as
 * externals by AdminJS's component bundler (AssetBundler.DEFAULT_EXTERNALS) —
 * they resolve to the `React` / `AdminJSDesignSystem` / `AdminJS` globals the
 * AdminJS frontend already ships, so this component adds no new dependency.
 *
 * Source: ADMIN_UI_SPEC.md §2.1; ADR-0019.
 */

import React, { useEffect, useState } from "react";
import { Box, H2, H4, H5, Text, Badge, Button, Illustration } from "@adminjs/design-system";
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

const STEPS: Step[] = [
  { key: "hasServices", title: "Register a backend service", ctaLabel: "Register a service", ctaHref: "/admin/resources/services/actions/new" },
  { key: "hasCredentials", title: "Add its credential and test it", ctaLabel: "Configure credentials", ctaHref: "/admin/resources/services" },
  { key: "hasAgents", title: "Create an agent", ctaLabel: "Create an agent", ctaHref: "/admin/resources/agents/actions/new" },
  { key: "hasPermissions", title: "Grant the agent a permission", ctaLabel: "Grant a permission", ctaHref: "/admin/resources/permission_grants/actions/new" },
  { key: "hasTested", title: "Connect your LLM to MCP", ctaLabel: "Show MCP config", ctaHref: "/admin/resources/agents" },
];

const ChecklistItem: React.FC<{ done: boolean; title: string; ctaLabel: string; ctaHref: string }> = ({ done, title, ctaLabel, ctaHref }) => (
  <Box flex alignItems="center" mb="lg" data-testid="dashboard-checklist-item">
    <Box mr="lg" style={{ fontSize: 22, lineHeight: "22px" }}>{done ? "☑" : "☐"}</Box>
    <Box flexGrow={1}>
      <Text fontWeight="bold">{title}</Text>
    </Box>
    {done ? (
      <Badge variant="success">done</Badge>
    ) : (
      <Button as="a" href={ctaHref} size="sm" variant="primary">{ctaLabel}</Button>
    )}
  </Box>
);

const Dashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loaded, setLoaded] = useState(false);

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
    <Box variant="grey">
      <Box variant="white" mb="xxl">
        <H2>Mintkey — credential broker for AI agents</H2>
        <Text>
          Operator <strong>{data?.email || "—"}</strong>
          {data?.tenantId ? <> &middot; tenant <strong>{data.tenantId}</strong></> : null}
        </Text>
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
  );
};

export default Dashboard;
