/**
 * AgentGrantsWarningPanel — show-page callout for agents with no permission grants (UX-FB-CE Part C).
 *
 * Rendered as a property.components.show override on a virtual `_grants_warning`
 * property placed at the top of the Agents show page.
 *
 * Displays a red callout when the agent is active but has zero permission grants.
 * Hides itself when:
 *   - grants_count > 0 (agent already has grants — nothing to warn)
 *   - status === "revoked" (revoked agents are handled by separate cascade warning)
 *
 * Source: UX-FB-CE Part C spec.
 */

import React from "react";
import { Box, Text } from "@adminjs/design-system";

interface Props {
  record?: { id?: string; params?: Record<string, unknown> };
}

const AgentGrantsWarningPanel: React.FC<Props> = ({ record }) => {
  const agentId = (record?.params?.id ?? record?.id ?? "") as string;
  const count = Number(record?.params?.grants_count ?? 0);
  const status = String(record?.params?.status ?? "");
  // Only warn when active + no grants. Revoked agents handled elsewhere.
  if (count > 0 || status === "revoked") return null;
  const newPermUrl = `/admin/resources/permission_grants/actions/new?agent_id=${encodeURIComponent(agentId)}`;
  return (
    <Box
      data-testid="agent-no-grants-warning"
      p="lg"
      mb="xl"
      style={{
        background: "#fff4f4",
        border: "1px solid #e85c5c",
        borderLeft: "4px solid #e85c5c",
        borderRadius: 4,
      }}
    >
      <Text style={{ fontWeight: 600, color: "#a52a2a", marginBottom: 4 }}>
        This agent has no permission grants.
      </Text>
      <Text style={{ fontSize: 13, color: "#5e1717" }}>
        The agent can authenticate but cannot call any service.
        {" "}
        <a href={newPermUrl} style={{ color: "#3795BE", textDecoration: "underline" }}>
          Grant a permission to this agent
        </a>
      </Text>
    </Box>
  );
};
export default AgentGrantsWarningPanel;
