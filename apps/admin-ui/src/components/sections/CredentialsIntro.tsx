/**
 * CredentialsIntro — list-action override for the Credentials resource.
 * Renders the Credentials intro paragraph and an inline search input above
 * the AdminJS list table (UX-B).
 * Source: admin-ui-ux-uplift chunk; UX-B.
 */

import React from "react";
import InlineSearchList from "../list/InlineSearchList.js";

const INTRO =
  "Credentials are the real secrets for a backend Service — the API key, the username/password, the OAuth client, the mTLS bundle — stored envelope-encrypted in the Vault Adapter. Agents never see these. The Egress Proxy fetches the Credential at request time and injects it into the outbound call. Each Credential is bound to exactly one Service. Rotate Credentials here; revocation is instant via the change channel.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CredentialsIntro = (props: Record<string, any>): React.ReactElement => (
  <InlineSearchList
    introText={INTRO}
    placeholder="Search by auth scheme"
    {...props}
  />
);

export default CredentialsIntro;
