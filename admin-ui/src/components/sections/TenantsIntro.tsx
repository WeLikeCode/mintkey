/**
 * TenantsIntro — list-action override for the Tenants resource.
 * Renders the Tenants intro paragraph above the AdminJS list.
 * Source: admin-ui-ux-uplift chunk.
 */

import React from "react";
import ResourceIntroList from "./ResourceIntroList.js";

const INTRO =
  "Tenants are isolated workspaces. Each tenant has its own Services, Credentials, Agents, Permission Grants, Service API Keys, and Audit log; row-level isolation is enforced at the application layer and by Postgres RLS. Operators belong to one or more tenants. PlatformAdmins manage tenants themselves and can reach across them. In single-tenant deployments you'll see only one tenant here — in multi-tenant deployments, this is where you create and configure them.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const TenantsIntro = (props: Record<string, any>): React.ReactElement => (
  <ResourceIntroList introText={INTRO} {...props} />
);

export default TenantsIntro;
