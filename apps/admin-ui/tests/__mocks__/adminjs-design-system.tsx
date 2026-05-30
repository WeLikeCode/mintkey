/**
 * Stub for @adminjs/design-system — used only by the jsdom render test harness.
 * Each component renders as a plain HTML element so data-testid attrs and text
 * content are accessible via @testing-library queries.
 */
import React from "react";

type AnyProps = Record<string, unknown> & { children?: React.ReactNode };

export const Box = ({ children, ...rest }: AnyProps) =>
  React.createElement("div", rest, children);

export const H3 = ({ children, ...rest }: AnyProps) =>
  React.createElement("h3", rest, children);

export const Text = ({ children, ...rest }: AnyProps) =>
  React.createElement("span", rest, children);

export const Button = ({
  children,
  onClick,
  type,
  disabled,
  ...rest
}: AnyProps & {
  onClick?: React.MouseEventHandler;
  type?: React.ButtonHTMLAttributes<HTMLButtonElement>["type"];
  disabled?: boolean;
}) => React.createElement("button", { onClick, type, disabled, ...rest }, children);

export const Input = ({
  value,
  onChange,
  placeholder,
  ...rest
}: AnyProps & {
  value?: string;
  onChange?: React.ChangeEventHandler<HTMLInputElement>;
  placeholder?: string;
}) => React.createElement("input", { value, onChange, placeholder, ...rest });

export const Label = ({
  children,
  htmlFor,
  ...rest
}: AnyProps & { htmlFor?: string }) =>
  React.createElement("label", { htmlFor, ...rest }, children);
