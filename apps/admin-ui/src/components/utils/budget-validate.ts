/**
 * Budget input validation utility.
 *
 * Validates ceiling, period, and thresholds before submission to the BFF.
 * Spec: .kiro/specs/budget-management-ui (Requirements 2.4, 2.5)
 */

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

const VALID_PERIODS = ["hourly", "daily", "weekly", "monthly"] as const;

/**
 * Validates budget form input.
 *
 * - Ceiling must be a positive integer (>= 1)
 * - Each threshold must be an integer in [1, 100]
 * - If ceiling or period is provided, both are required
 */
export function validateBudgetInput(
  ceiling: unknown,
  period: unknown,
  thresholds: unknown[]
): ValidationResult {
  const errors: string[] = [];

  const ceilingProvided = ceiling !== undefined;
  const periodProvided = period !== undefined;

  // Co-dependency: if one is provided, both are required
  if (ceilingProvided && !periodProvided) {
    errors.push("Period is required when ceiling is provided");
  }
  if (periodProvided && !ceilingProvided) {
    errors.push("Ceiling is required when period is provided");
  }

  // Validate ceiling (only if provided)
  if (ceilingProvided) {
    if (
      typeof ceiling !== "number" ||
      !Number.isFinite(ceiling) ||
      !Number.isInteger(ceiling) ||
      ceiling < 1
    ) {
      errors.push("Ceiling must be a positive integer (>= 1)");
    }
  }

  // Validate period (only if provided)
  if (periodProvided) {
    if (
      typeof period !== "string" ||
      !(VALID_PERIODS as readonly string[]).includes(period)
    ) {
      errors.push(
        "Period must be one of: hourly, daily, weekly, monthly"
      );
    }
  }

  // Validate thresholds
  for (let i = 0; i < thresholds.length; i++) {
    const t = thresholds[i];
    if (
      typeof t !== "number" ||
      !Number.isFinite(t) ||
      !Number.isInteger(t) ||
      t < 1 ||
      t > 100
    ) {
      errors.push(`Threshold at index ${i} must be an integer in [1, 100]`);
    }
  }

  return { valid: errors.length === 0, errors };
}
