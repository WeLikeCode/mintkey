/**
 * Key expiry formatting utilities — UX-FB-AK-2.
 *
 * Pure functions; no React dependency so they can be used in both UI components
 * and node-environment unit tests.
 */

export type ExpiryTone = "ok" | "warn" | "danger" | "expired" | "never";

export interface FormattedExpiry {
  label: string;
  tone: ExpiryTone;
  absolute: string;
}

/**
 * Format an ISO timestamp (or null) into a human-readable relative label.
 *
 * - null / undefined  → { label: "Never", tone: "never", absolute: "" }
 * - past              → { label: "Expired N units ago", tone: "expired", ... }
 * - future < 7 days   → { label: "in N units", tone: "warn", ... }
 * - future >= 7 days  → { label: "in N units", tone: "ok", ... }
 */
export function formatRelativeExpiry(iso: string | null | undefined): FormattedExpiry {
  if (!iso) return { label: "Never", tone: "never", absolute: "" };
  const target = new Date(iso);
  if (Number.isNaN(target.getTime())) return { label: "Invalid", tone: "warn", absolute: iso };
  const nowMs = Date.now();
  const diffMs = target.getTime() - nowMs;
  const absDiff = Math.abs(diffMs);
  const sec = Math.round(absDiff / 1000);
  const min = Math.round(sec / 60);
  const hr = Math.round(min / 60);
  const day = Math.round(hr / 24);

  let unit: string;
  let value: number;
  if (sec < 60) { unit = "seconds"; value = sec; }
  else if (min < 60) { unit = "minute" + (min === 1 ? "" : "s"); value = min; }
  else if (hr < 48) { unit = "hour" + (hr === 1 ? "" : "s"); value = hr; }
  else { unit = "day" + (day === 1 ? "" : "s"); value = day; }

  const absolute = target.toISOString();

  if (diffMs < 0) {
    return { label: `Expired ${value} ${unit} ago`, tone: "expired", absolute };
  }
  const days = diffMs / 86_400_000;
  const tone: ExpiryTone = days < 7 ? "warn" : "ok";
  return { label: `in ${value} ${unit}`, tone, absolute };
}
