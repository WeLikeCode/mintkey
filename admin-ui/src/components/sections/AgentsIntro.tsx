/**
 * AgentsIntro — list-action override for the Agents resource.
 * Renders the Agents intro paragraph and an inline search input above the
 * AdminJS list table (UX-B).
 * Source: admin-ui-ux-uplift chunk; UX-B.
 */

import React from "react";
import InlineSearchList from "../list/InlineSearchList.js";

const INTRO =
  "Agents are the AI agents (or systems acting on their behalf) that consume Mintkey. Each Agent has a unique identity and uses a short-lived brokered JWT (default 10 minutes) to authenticate. To call a backend Service, an Agent must have a Permission Grant on that Service. Revoking an Agent immediately kills its access to every Service it was granted — no token TTL waiting.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const AgentsIntro = (props: Record<string, any>): React.ReactElement => (
  <InlineSearchList
    introText={INTRO}
    placeholder="Search by name or description"
    {...props}
  />
);

export default AgentsIntro;
