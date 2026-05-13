/**
 * ResourceIntroList — generic wrapper component for AdminJS list views.
 *
 * Renders a per-resource intro paragraph above the standard AdminJS list.
 * Used by all 7 resource definitions to inject contextual explanations without
 * touching any list rendering logic. Registered via ComponentLoader and wired
 * to each resource's `options.actions.list.component`.
 *
 * The intro text is passed from each resource-specific intro wrapper component
 * (sections/*Intro.tsx). The actual list is rendered using AdminJS's exported
 * `List` component so no list functionality is lost.
 *
 * AdminJS 7.x bundles this via AssetBundler — react/@adminjs/design-system/adminjs
 * are externals resolved to global variables at runtime. Type annotations here
 * mirror the pre-existing pattern in Dashboard.tsx (same externals, no @types/react).
 *
 * Source: admin-ui-ux-uplift chunk; ADMIN_UI_SPEC.md §2.x.
 */

import React from "react";
import { Box, Text } from "@adminjs/design-system";
import { List } from "adminjs";

// Mirror the pre-existing pattern: externals are untyped, use loose signature
// (consistent with how Dashboard.tsx is written — no @types/react installed)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ResourceIntroList = (props: Record<string, any>): React.ReactElement => {
  const { introText, ...listProps } = props;
  return (
    <Box>
      <Box
        variant="white"
        mb="default"
        p="xl"
        style={{
          borderLeft: "4px solid #3795BE",
          background: "#f0f7fb",
        }}
        data-testid="resource-intro-banner"
      >
        <Text style={{ lineHeight: 1.6, color: "#2c3e50", margin: 0 }}>{introText}</Text>
      </Box>
      {/* Cast is safe: AdminJS passes all ActionProps at runtime via ComponentLoader */}
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <List {...(listProps as any)} />
    </Box>
  );
};

export default ResourceIntroList;
