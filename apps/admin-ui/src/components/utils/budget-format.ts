/**
 * Budget formatting utilities.
 *
 * Pure functions for converting budget period data into human-readable display strings.
 */

/**
 * Formats a budget period into a human-readable string.
 *
 * @param period - Budget period type (hourly, daily, weekly, monthly)
 * @param periodStart - ISO 8601 UTC timestamp for period start
 * @param periodEnd - ISO 8601 UTC timestamp for period end
 * @returns Human-readable string, e.g. "Daily: Jun 15, 2026 00:00 UTC – Jun 16, 2026 00:00 UTC"
 */
export function formatPeriod(
  period: string,
  periodStart: string,
  periodEnd: string
): string {
  const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
  const formatDate = (iso: string) => {
    const d = new Date(iso);
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];
    const month = months[d.getUTCMonth()];
    const day = d.getUTCDate();
    const year = d.getUTCFullYear();
    const hours = String(d.getUTCHours()).padStart(2, "0");
    const minutes = String(d.getUTCMinutes()).padStart(2, "0");
    return `${month} ${day}, ${year} ${hours}:${minutes} UTC`;
  };

  return `${capitalize(period)}: ${formatDate(periodStart)} \u2013 ${formatDate(periodEnd)}`;
}
