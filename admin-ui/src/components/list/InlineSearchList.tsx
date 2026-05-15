/**
 * InlineSearchList — list-action override component with a prominent inline
 * search input above the AdminJS list table.
 *
 * Strategy: option (c) — update `filters.q` in the URL using React Router's
 * `useSearchParams` (via `qs` stringify, matching AdminJS's own format) so that
 * AdminJS's `useRecords` hook re-fetches when the search params change.
 *
 * The component is bundled by AdminJS's ComponentLoader — `react`,
 * `@adminjs/design-system`, `react-router-dom`, and `adminjs` are externals
 * resolved at runtime (same pattern as ApiKeyCreate.tsx).
 *
 * Layout:
 *   +─────────────────────────────────+
 *   | [intro banner if introText]     |
 *   +─────────────────────────────────+
 *   | 🔍  <search input>          [x] |
 *   +─────────────────────────────────+
 *   | … AdminJS default list table … |
 *   +─────────────────────────────────+
 *
 * Props:
 *   placeholder  — per-resource hint text shown in the input
 *   introText    — optional explanatory paragraph (forwarded from *Intro.tsx
 *                  wrappers; renders the existing intro banner above the search)
 *   ...rest      — all AdminJS action props forwarded to <List />
 *
 * Source: UX-B; admin-ui-ux-uplift chunk.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Box, Text, Input, Icon } from "@adminjs/design-system";
import { List } from "adminjs";
import { useSearchParams } from "react-router-dom";

// qs is bundled with adminjs and available as a global-like in the bundle
// We use URLSearchParams for read and useSearchParams for write.

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const InlineSearchList = (props: Record<string, any>): React.ReactElement => {
  const { placeholder, introText, ...listProps } = props;
  const [searchParams, setSearchParams] = useSearchParams();

  // Read current q value from URL search params
  // AdminJS stores filters as `filters[q]` or `filters.q` depending on qs parse mode.
  // We read both forms.
  const getQFromParams = useCallback((): string => {
    // Try `filters.q` (dot notation) or `filters[q]` (bracket notation)
    return (
      searchParams.get("filters.q") ??
      searchParams.get("filters[q]") ??
      ""
    );
  }, [searchParams]);

  const [inputValue, setInputValue] = useState<string>(() => getQFromParams());
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync local state when URL changes externally (browser back/forward)
  useEffect(() => {
    setInputValue(getQFromParams());
  }, [searchParams, getQFromParams]);

  const applySearch = useCallback((value: string) => {
    // Build new search params: preserve all existing params, set/delete filters.q
    const next = new URLSearchParams(searchParams.toString());
    if (value.trim() === "") {
      next.delete("filters.q");
      next.delete("filters[q]");
    } else {
      next.set("filters.q", value.trim());
    }
    // Reset to page 1 when filter changes
    next.delete("page");
    setSearchParams(next, { replace: false });
  }, [searchParams, setSearchParams]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputValue(val);

    if (debounceTimer.current !== null) {
      clearTimeout(debounceTimer.current);
    }
    debounceTimer.current = setTimeout(() => {
      applySearch(val);
    }, 300);
  }, [applySearch]);

  const handleClear = useCallback(() => {
    setInputValue("");
    if (debounceTimer.current !== null) {
      clearTimeout(debounceTimer.current);
    }
    applySearch("");
  }, [applySearch]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimer.current !== null) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, []);

  const resolvedPlaceholder =
    typeof placeholder === "string" && placeholder.length > 0
      ? placeholder
      : "Search…";

  return (
    <Box>
      {/* Optional intro banner — rendered when introText is provided */}
      {introText ? (
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
          <Text style={{ lineHeight: 1.6, color: "#2c3e50", margin: 0 }}>
            {introText}
          </Text>
        </Box>
      ) : null}

      {/* Inline search bar */}
      <Box
        mb="default"
        p="default"
        variant="white"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          border: "1px solid #e0e0e0",
          borderRadius: "4px",
          background: "#ffffff",
        }}
        data-testid="inline-search-box"
      >
        <Icon icon="Search" size={16} color="grey60" />
        <Input
          value={inputValue}
          onChange={handleChange}
          placeholder={resolvedPlaceholder}
          data-testid="inline-search-input"
          style={{
            flex: 1,
            border: "none",
            outline: "none",
            fontSize: "14px",
            background: "transparent",
          }}
        />
        {inputValue.length > 0 ? (
          <Icon
            icon="X"
            size={14}
            color="grey60"
            style={{ cursor: "pointer" }}
            onClick={handleClear}
          />
        ) : null}
      </Box>

      {/* AdminJS list table — receives all original action props */}
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <List {...(listProps as any)} />
    </Box>
  );
};

export default InlineSearchList;
