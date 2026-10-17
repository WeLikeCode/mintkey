/**
 * Labels of the admin UI's properties and actions.
 *
 * AdminJS 7 takes a display name only from its locale — `resources.<id>.properties.<path>` and
 * `resources.<id>.actions.<name>`, which a resource's own `options.translations` fills — and ignores a `label` in a
 * property's or an action's options (its types have no such key). The resources keep each label next to the field or
 * action it names; `withLabelTranslations` copies them into `options.translations` when `index.ts` hands the
 * resources to AdminJS, so they are what the UI shows.
 */

import type { Action, ActionResponse, PropertyOptions, ResourceOptions, ResourceWithOptions } from "adminjs";

/** A property's AdminJS options and the label the UI shows for it. */
export type LabeledPropertyOptions = PropertyOptions & { label?: string };

/** An action's AdminJS options and the label of its button or link. */
export type LabeledActionOptions = Partial<Action<ActionResponse>> & { label?: string };

/** A resource's AdminJS options whose properties and actions may carry a `label`. */
export interface LabeledResourceOptions extends Omit<ResourceOptions, "properties" | "actions"> {
  properties?: Record<string, LabeledPropertyOptions>;
  actions?: Record<string, LabeledActionOptions>;
}

/** A resource as `src/resources/*` declares it: the AdminJS resource, its adapter instance and labeled options. */
export type LabeledResource<A> = Omit<ResourceWithOptions, "options"> & {
  adminResource: A;
  options: LabeledResourceOptions;
};

const LANGUAGE = "en";

function labels(entries: Record<string, { label?: string }> | undefined): Record<string, string> {
  const found: Record<string, string> = {};
  for (const [key, value] of Object.entries(entries ?? {})) {
    if (value.label) found[key] = value.label;
  }
  return found;
}

function block(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

/**
 * The resource's options with every property and action `label` in `options.translations.en`, where AdminJS reads
 * them. A translation the resource already declares for the same key wins over its label.
 */
export function withLabelTranslations(options: LabeledResourceOptions): ResourceOptions {
  const properties = labels(options.properties);
  const actions = labels(options.actions);
  if (Object.keys(properties).length === 0 && Object.keys(actions).length === 0) return options;
  const existing = block(options.translations?.[LANGUAGE]);
  return {
    ...options,
    translations: {
      ...options.translations,
      [LANGUAGE]: {
        ...existing,
        properties: { ...properties, ...block(existing["properties"]) },
        actions: { ...actions, ...block(existing["actions"]) },
      },
    },
  };
}
