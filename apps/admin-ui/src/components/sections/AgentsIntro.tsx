/**
 * AgentsIntro — list-action override for the Agents resource.
 * Renders the Agents intro paragraph and an inline search input above the
 * AdminJS list table (UX-B).
 * Source: admin-ui-ux-uplift chunk; UX-B; UX-CLARITY chunk C.
 */

import React from "react";
import { Box, Text } from "@adminjs/design-system";
import InlineSearchList from "../list/InlineSearchList.js";

const WHAT_IS_AGENT =
  "An agent is an AI client identity. Each agent has an API key that authenticates it to the MCP server. Use the MCP Endpoint URL on the show page to connect your AI client.";

const INTRO =
  "Agents are the AI agents (or systems acting on their behalf) that consume Mintkey. Each Agent has a unique identity and uses a short-lived brokered JWT (default 10 minutes) to authenticate. To call a backend Service, an Agent must have a Permission Grant on that Service. Revoking an Agent immediately kills its access to every Service it was granted — no token TTL waiting.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const AgentsIntro = (props: Record<string, any>): React.ReactElement => (
  <Box>
    {/* UX-CLARITY chunk C: "what is an agent" primer at the top of the list page */}
    <Box
      variant="white"
      mb="default"
      p="xl"
      style={{
        borderLeft: "4px solid #3795BE",
        background: "#f0f7fb",
      }}
      data-testid="agents-what-is-banner"
    >
      <Text
        style={{ lineHeight: 1.6, color: "#2c3e50", margin: 0, marginBottom: "8px", fontWeight: 500 }}
        data-testid="agents-what-is-paragraph"
      >
        {WHAT_IS_AGENT}
      </Text>
      <Text style={{ lineHeight: 1.6, color: "#2c3e50", margin: 0 }}>
        {INTRO}
      </Text>
    </Box>
    <InlineSearchList
      placeholder="Search by name or description"
      {...props}
    />
  </Box>
);

export default AgentsIntro;
