/**
 * AsyncCombobox — typeahead combobox backed by an AdminJS resource list endpoint.
 *
 * Replaces plain `<select>` dropdowns (and text inputs) with a typeahead UI that
 * lets operators filter options by name OR id in real time.
 *
 * Props:
 *   resourceId   — AdminJS resource id to query (e.g. "agents", "services")
 *   value        — current wire-id value (empty string = nothing selected)
 *   onChange     — called with the selected wire-id; called with "" on clear
 *   placeholder  — input placeholder
 *   labelFor     — (optional) how to format each option; default: "${name} (${id})"
 *   staticOptions — (optional) pre-computed option list; when provided the component
 *                   does NOT call the AdminJS API — it just filters this list locally.
 *                   Satisfies the agent-permissions intersection constraint in
 *                   ApiKeyCreate without a second network call.
 *   disabled     — grey-out and prevent interaction
 *
 * Behaviour:
 *   - On mount (no staticOptions): fetches top-50 records for the initial dropdown.
 *   - On type (no staticOptions): debounce 300ms, calls api.resourceAction list with
 *     filters.q = typed text.
 *   - On type (with staticOptions): local filter only; no network call.
 *   - Selected value shown as a removable chip above the input.
 *   - Keyboard: ArrowDown/Up to highlight, Enter to pick, Esc to close.
 *   - Click outside closes the dropdown.
 *   - If value is set on mount but the initial list hasn't loaded yet, a synthetic
 *     "(loading…)" label is shown until the first list call resolves.
 *
 * Design-system primitives: Box, Input, Text (no new UI library).
 *
 * Source: UX-A spec; admin-ui-ux-uplift Wave 2.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Box, Input, Text } from "@adminjs/design-system";
import { ApiClient } from "adminjs";

// ── types ─────────────────────────────────────────────────────────────────────

export interface ComboboxOption {
  value: string; // wire-id
  label: string; // display label, e.g. "My Agent (agent_XXXX)"
}

export interface AsyncComboboxProps {
  resourceId: string;
  value: string;
  onChange: (wireId: string) => void;
  placeholder?: string;
  /** Override label format; receives the AdminJS record params object. */
  labelFor?: (params: Record<string, unknown>) => string;
  /** When provided, skip API calls and filter this list locally. */
  staticOptions?: ComboboxOption[];
  disabled?: boolean;
  /** data-testid prefix — defaults to `combobox-${resourceId}` */
  testId?: string;
}

// ── default label ─────────────────────────────────────────────────────────────

function defaultLabelFor(params: Record<string, unknown>): string {
  const name = (params.name as string) ?? "";
  const id = (params.id as string) ?? "";
  return name ? `${name} (${id})` : id;
}

// ── component ─────────────────────────────────────────────────────────────────

const AsyncCombobox: React.FC<AsyncComboboxProps> = ({
  resourceId,
  value,
  onChange,
  placeholder = "Type to search…",
  labelFor,
  staticOptions,
  disabled = false,
  testId,
}) => {
  const resolvedTestId = testId ?? `combobox-${resourceId}`;
  const formatLabel = labelFor ?? defaultLabelFor;

  // ── state ──────────────────────────────────────────────────────────────────
  const [inputText, setInputText] = useState("");
  const [options, setOptions] = useState<ComboboxOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [highlightedIdx, setHighlightedIdx] = useState(-1);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);

  // ── refs ───────────────────────────────────────────────────────────────────
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // ── helpers: resolve label for current value ───────────────────────────────
  const findLabelInList = useCallback(
    (opts: ComboboxOption[], wireId: string): string | null => {
      const found = opts.find((o) => o.value === wireId);
      return found ? found.label : null;
    },
    []
  );

  // ── initial load (dynamic mode only) ──────────────────────────────────────
  useEffect(() => {
    if (staticOptions !== undefined) {
      // Static mode: no API calls needed
      setOptions(staticOptions);
      if (value) {
        const lbl = findLabelInList(staticOptions, value);
        setSelectedLabel(lbl ?? `(${value})`);
      } else {
        setSelectedLabel(null);
      }
      return;
    }

    // Dynamic mode: fetch initial 50 records
    let cancelled = false;
    setLoading(true);

    const api = new ApiClient();
    void api
      .resourceAction({
        resourceId,
        actionName: "list",
        method: "get",
        params: { perPage: 50 },
      })
      .then((resp) => {
        if (cancelled) return;
        const data = resp.data as {
          records?: Array<{ params: Record<string, unknown> }>;
        };
        const opts: ComboboxOption[] = (data.records ?? []).map((r) => ({
          value: String(r.params.id ?? ""),
          label: formatLabel(r.params),
        }));
        setOptions(opts);
        // Resolve label for pre-selected value once list arrives
        if (value) {
          const lbl = findLabelInList(opts, value);
          setSelectedLabel(lbl ?? `(${value})`);
        }
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceId]); // intentionally run only on mount

  // ── sync selectedLabel when value changes externally ──────────────────────
  useEffect(() => {
    if (!value) {
      setSelectedLabel(null);
      return;
    }
    const lbl = findLabelInList(options, value);
    if (lbl) {
      setSelectedLabel(lbl);
    } else if (selectedLabel === null) {
      // Value set but list not loaded yet — show "(loading…)" until list arrives
      setSelectedLabel("(loading…)");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, options]);

  // ── debounced search (dynamic mode) ──────────────────────────────────────
  const doSearch = useCallback(
    (text: string) => {
      if (staticOptions !== undefined) return; // static mode: filter handled below

      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
      }

      debounceRef.current = setTimeout(() => {
        const api = new ApiClient();
        setLoading(true);
        void api
          .resourceAction({
            resourceId,
            actionName: "list",
            method: "get",
            params: {
              perPage: 50,
              filters: text.trim() ? { q: text.trim() } : {},
            },
          })
          .then((resp) => {
            const data = resp.data as {
              records?: Array<{ params: Record<string, unknown> }>;
            };
            const opts: ComboboxOption[] = (data.records ?? []).map((r) => ({
              value: String(r.params.id ?? ""),
              label: formatLabel(r.params),
            }));
            setOptions(opts);
            setHighlightedIdx(-1);
            setLoading(false);
          })
          .catch(() => setLoading(false));
      }, 300);
    },
    [resourceId, formatLabel, staticOptions]
  );

  // ── computed filtered list (static mode) ─────────────────────────────────
  const visibleOptions =
    staticOptions !== undefined
      ? staticOptions.filter((o) => {
          if (!inputText.trim()) return true;
          const q = inputText.toLowerCase();
          return (
            o.label.toLowerCase().includes(q) ||
            o.value.toLowerCase().includes(q)
          );
        })
      : options;

  // ── event handlers ─────────────────────────────────────────────────────────

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputText(val);
    setOpen(true);
    setHighlightedIdx(-1);
    doSearch(val);
  };

  const handleInputFocus = () => {
    if (!disabled) setOpen(true);
  };

  // onClick also opens the dropdown — handles the case where the input already
  // has focus (re-click after Esc close) where focus event doesn't re-fire.
  const handleInputClick = () => {
    if (!disabled) setOpen(true);
  };

  const handleSelect = (opt: ComboboxOption) => {
    onChange(opt.value);
    setSelectedLabel(opt.label);
    setInputText("");
    setOpen(false);
    setHighlightedIdx(-1);
  };

  const handleClear = () => {
    onChange("");
    setSelectedLabel(null);
    setInputText("");
    setOpen(false);
    setHighlightedIdx(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        setOpen(true);
        e.preventDefault();
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIdx((idx) =>
        Math.min(idx + 1, visibleOptions.length - 1)
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIdx((idx) => Math.max(idx - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIdx >= 0 && highlightedIdx < visibleOptions.length) {
        handleSelect(visibleOptions[highlightedIdx]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setHighlightedIdx(-1);
    }
  };

  // ── click outside ─────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setHighlightedIdx(-1);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── scroll highlighted item into view ────────────────────────────────────
  useEffect(() => {
    if (highlightedIdx < 0 || !listRef.current) return;
    const item = listRef.current.children[highlightedIdx] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest" });
  }, [highlightedIdx]);

  // ── cleanup timer ─────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) clearTimeout(debounceRef.current);
    };
  }, []);

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div
      ref={containerRef}
      style={{ position: "relative" }}
      data-testid={resolvedTestId}
    >
      {/* Selected-value chip */}
      {selectedLabel !== null && (
        <Box
          mb="sm"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            background: "#e8f4fb",
            border: "1px solid #3795BE",
            borderRadius: 4,
            padding: "2px 10px 2px 8px",
            fontSize: 13,
            color: "#1a567d",
          }}
          data-testid={`${resolvedTestId}-chip`}
        >
          <span data-testid={`${resolvedTestId}-chip-label`}>{selectedLabel}</span>
          {!disabled && (
            <span
              onClick={handleClear}
              style={{
                cursor: "pointer",
                fontWeight: 700,
                color: "#3795BE",
                marginLeft: 4,
                lineHeight: 1,
              }}
              aria-label="Clear selection"
              data-testid={`${resolvedTestId}-clear`}
            >
              ×
            </span>
          )}
        </Box>
      )}

      {/* Search input */}
      <Input
        value={inputText}
        onChange={handleInputChange}
        onFocus={handleInputFocus}
        onClick={handleInputClick}
        onKeyDown={handleKeyDown}
        placeholder={selectedLabel !== null ? "Change selection…" : placeholder}
        disabled={disabled}
        data-testid={`${resolvedTestId}-input`}
        style={{ width: "100%" }}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-haspopup="listbox"
        role="combobox"
      />

      {/* Dropdown list */}
      {open && (
        <ul
          ref={listRef}
          role="listbox"
          data-testid={`${resolvedTestId}-dropdown`}
          style={{
            position: "absolute",
            top: "calc(100% + 2px)",
            left: 0,
            right: 0,
            zIndex: 1000,
            maxHeight: 240,
            overflowY: "auto",
            margin: 0,
            padding: 0,
            listStyle: "none",
            background: "#fff",
            border: "1px solid #dee2e6",
            borderRadius: 4,
            boxShadow: "0 4px 12px rgba(0,0,0,0.12)",
          }}
        >
          {loading && (
            <li
              style={{
                padding: "8px 12px",
                color: "#6c757d",
                fontSize: 13,
              }}
              data-testid={`${resolvedTestId}-loading`}
            >
              Loading…
            </li>
          )}

          {!loading && visibleOptions.length === 0 && (
            <li
              style={{
                padding: "8px 12px",
                color: "#6c757d",
                fontSize: 13,
              }}
              data-testid={`${resolvedTestId}-empty`}
            >
              No results
            </li>
          )}

          {!loading &&
            visibleOptions.map((opt, idx) => (
              <li
                key={opt.value}
                role="option"
                aria-selected={opt.value === value}
                onMouseDown={(e) => {
                  // prevent blur before click registers
                  e.preventDefault();
                  handleSelect(opt);
                }}
                style={{
                  padding: "8px 12px",
                  fontSize: 13,
                  cursor: "pointer",
                  background:
                    idx === highlightedIdx
                      ? "#e8f4fb"
                      : opt.value === value
                      ? "#f0f7fb"
                      : "transparent",
                  color: opt.value === value ? "#1a567d" : "#212529",
                  fontWeight: opt.value === value ? 600 : 400,
                  borderBottom:
                    idx < visibleOptions.length - 1
                      ? "1px solid #f1f3f5"
                      : "none",
                }}
                data-testid={`${resolvedTestId}-option-${idx}`}
                data-value={opt.value}
              >
                {opt.label}
              </li>
            ))}
        </ul>
      )}

      {/* Hidden input carrying the wire-id value for native form submission */}
      <input
        type="hidden"
        value={value}
        data-testid={`${resolvedTestId}-value`}
        readOnly
      />
    </div>
  );
};

export default AsyncCombobox;
