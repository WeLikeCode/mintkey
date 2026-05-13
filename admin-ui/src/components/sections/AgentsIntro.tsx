/**
 * AgentsIntro — list-action override for the Agents resource.
 * Source: admin-ui-ux-uplift chunk.
 */

import React from "react";
import ResourceIntroList from "./ResourceIntroList.js";

const INTRO =
  "Agents are the AI agents (or systems acting on their behalf) that consume Mintkey. Each Agent has a unique identity and uses a short-lived brokered JWT (default 10 minutes) to authenticate. To call a backend Service, an Agent must have a Permission Grant on that Service. Revoking an Agent immediately kills its access to every Service it was granted — no token TTL waiting.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const AgentsIntro = (props: Record<string, any>): React.ReactElement => (
  <ResourceIntroList introText={INTRO} {...props} />
);

export default AgentsIntro;
