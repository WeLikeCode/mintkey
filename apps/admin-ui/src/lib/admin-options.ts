/**
 * Typed builders for the AdminJS resource options in src/resources/*.
 *
 * The resource files annotate properties with a display `label` and scope
 * visibility with `isVisible.new`, and label actions with `label`. AdminJS
 * 7.8's own types (PropertyOptions, the isVisible object, Action) declare none
 * of these keys: its PropertyDecorator.isVisible() only reads list, show, edit
 * and filter, and labels come from locale translations. The keys are
 * documentation of intent that the code and the unit tests already rely on, so
 * they are declared here instead of being removed or silenced with casts.
 *
 * The builders are identity functions. Every Mintkey option type is a
 * structural supertype-extension of the AdminJS one, so the result is assigned
 * to the AdminJS type without any cast.
 */

import type { Action, ActionResponse, PropertyOptions } from "adminjs";

/** AdminJS property options plus the Mintkey-only `label` and `isVisible.new`. */
export type MintkeyPropertyOptions = Omit<PropertyOptions, "isVisible"> & {
  label?: string;
  isVisible?:
    | boolean
    | {
        show?: boolean;
        list?: boolean;
        edit?: boolean;
        filter?: boolean;
        new?: boolean;
      };
};

/** AdminJS action options plus the Mintkey-only `label`. */
export type MintkeyActionOptions = Partial<Action<ActionResponse>> & {
  label?: string;
};

export function propertyOptions(
  properties: Record<string, MintkeyPropertyOptions>
): Record<string, PropertyOptions> {
  return properties;
}

export function actionOptions(
  actions: Record<string, MintkeyActionOptions>
): Record<string, Partial<Action<ActionResponse>>> {
  return actions;
}
