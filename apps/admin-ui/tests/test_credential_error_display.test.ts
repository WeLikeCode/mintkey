/**
 * C-2: Field-level validation error display on credential register.
 *
 * Tests verify extractFieldErrors parses all shapes admin-api emits:
 *   1. Pydantic ValidationError detail array from ssh_password / ssh_private_key
 *      paths — loc has variable depth; last string segment is the field name.
 *   2. String detail (legacy apple_jwt / google_service_account paths) →
 *      returns {} so caller falls back to the top-level title/detail string.
 *   3. Missing / undefined body → returns {}.
 *   4. Multiple field errors in a single response.
 *   5. Nested loc (e.g. ["body", "value", "username"]) — last string wins.
 *
 * Source: C-2 chunk goal; admin_api.api.credentials ValidationError shapes.
 */

import { describe, it, expect } from "vitest";
import {
  extractFieldErrors,
  type AdminApiErrorResponse,
  type PydanticErrorDetail,
} from "../src/lib/credential-errors.js";

// ── helper: build a pydantic-style detail entry ──────────────────────────────
function mkDetail(loc: (string | number)[], msg: string): PydanticErrorDetail {
  return { loc, msg, type: "value_error" };
}

// ── extractFieldErrors ────────────────────────────────────────────────────────

describe("extractFieldErrors", () => {
  it("returns {} for undefined input", () => {
    expect(extractFieldErrors(undefined)).toEqual({});
  });

  it("returns {} when detail is missing", () => {
    const body: AdminApiErrorResponse = { type: "about:blank", title: "validation error" };
    expect(extractFieldErrors(body)).toEqual({});
  });

  it("returns {} when detail is a plain string (legacy path)", () => {
    const body: AdminApiErrorResponse = {
      type: "about:blank",
      title: "validation error",
      detail: "ssh_password value must be a valid JSON object",
    };
    expect(extractFieldErrors(body)).toEqual({});
  });

  it("extracts simple single-segment loc", () => {
    const body: AdminApiErrorResponse = {
      type: "about:blank",
      title: "validation error",
      detail: [mkDetail(["username"], "must be a non-empty string")],
    };
    expect(extractFieldErrors(body)).toEqual({
      username: "must be a non-empty string",
    });
  });

  it("extracts last string from deep loc path (pydantic v2 nesting)", () => {
    // Pydantic v2 can emit ["body", "value", "password"] for nested models
    const body: AdminApiErrorResponse = {
      type: "about:blank",
      title: "validation error",
      detail: [mkDetail(["body", "value", "password"], "String should have at least 1 character")],
    };
    expect(extractFieldErrors(body)).toEqual({
      password: "String should have at least 1 character",
    });
  });

  it("extracts multiple field errors from a single response", () => {
    const body: AdminApiErrorResponse = {
      type: "about:blank",
      title: "validation error",
      detail: [
        mkDetail(["username"], "Value error, username must not be empty"),
        mkDetail(["target_address"], "Value error, must be host:port with numeric port"),
        mkDetail(["password"], "String should have at least 1 character"),
      ],
    };
    expect(extractFieldErrors(body)).toEqual({
      username: "Value error, username must not be empty",
      target_address: "Value error, must be host:port with numeric port",
      password: "String should have at least 1 character",
    });
  });

  it("uses first error when the same field appears more than once", () => {
    const body: AdminApiErrorResponse = {
      detail: [
        mkDetail(["username"], "first error"),
        mkDetail(["username"], "second error"),
      ],
    };
    expect(extractFieldErrors(body)).toEqual({ username: "first error" });
  });

  it("skips entries with no string segment in loc (e.g. pure numeric index)", () => {
    const body: AdminApiErrorResponse = {
      detail: [
        mkDetail([0, 1, 2], "some list error"),
        mkDetail(["target_address"], "must be host:port"),
      ],
    };
    // The numeric-only entry is skipped; the string entry is captured
    expect(extractFieldErrors(body)).toEqual({ target_address: "must be host:port" });
  });

  it("handles ssh_private_key field names (private_key_pem, ssh_user)", () => {
    const body: AdminApiErrorResponse = {
      detail: [
        mkDetail(["private_key_pem"], "must start with -----BEGIN"),
        mkDetail(["ssh_user"], "must not be empty"),
      ],
    };
    expect(extractFieldErrors(body)).toEqual({
      private_key_pem: "must start with -----BEGIN",
      ssh_user: "must not be empty",
    });
  });

  it("returns {} for empty detail array", () => {
    const body: AdminApiErrorResponse = { detail: [] };
    expect(extractFieldErrors(body)).toEqual({});
  });
});
