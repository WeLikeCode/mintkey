/**
 * ServicesIntro — list-action override for the Services resource.
 * Renders the Services intro paragraph and an inline search input above the
 * AdminJS list table (UX-B).
 * Source: admin-ui-ux-uplift chunk; UX-B.
 */

import React from "react";
import InlineSearchList from "../list/InlineSearchList.js";

const INTRO =
  "Services are the backend APIs you've registered with Mintkey for an Agent to call. Each Service has a base URL, an auth scheme (API key, basic auth, OAuth, mTLS, none), and optional metadata. Mintkey never exposes the Service directly to Agents — Agents call it through the Egress Proxy, which injects the real Credential in-flight. Pair every Service with a Credential, then grant access to specific Agents via Permission Grants.";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ServicesIntro = (props: Record<string, any>): React.ReactElement => (
  <InlineSearchList
    introText={INTRO}
    placeholder="Search by name, slug, base URL"
    {...props}
  />
);

export default ServicesIntro;
