/**
 * PlatformAdmin middleware tests — T-1.12.4.
 *
 * Tests:
 * - Tenants resource is visible to PlatformAdmin only.
 * - isPlatformAdminView returns true only when both flags are set.
 * - platformAdminMiddleware sets platformAdminView when ?all_tenants=true.
 *
 * Source: T-1.12.4; Req 13 AC1, AC6; ADR-0016.3.
 */

import { describe, it, expect, vi } from "vitest";
import { isPlatformAdminView, platformAdminMiddleware } from "../src/middleware/platform-admin.js";
import type { Request, Response } from "express";

function makeReq(overrides: Partial<Request> = {}): Request {
  return {
    session: {},
    query: {},
    ...overrides,
  } as unknown as Request;
}

describe("isPlatformAdminView", () => {
  it("returns false when session has no isPlatformAdmin", () => {
    const req = makeReq({ session: { isPlatformAdmin: false } as Record<string, unknown> });
    expect(isPlatformAdminView(req)).toBe(false);
  });

  it("returns false when isPlatformAdmin=true but platformAdminView=false", () => {
    const req = makeReq({
      session: { isPlatformAdmin: true, platformAdminView: false } as Record<string, unknown>,
    });
    expect(isPlatformAdminView(req)).toBe(false);
  });

  it("returns true when both flags are true", () => {
    const req = makeReq({
      session: { isPlatformAdmin: true, platformAdminView: true } as Record<string, unknown>,
    });
    expect(isPlatformAdminView(req)).toBe(true);
  });
});

describe("platformAdminMiddleware", () => {
  it("sets platformAdminView=true when ?all_tenants=true and is PlatformAdmin", () => {
    const req = makeReq({
      query: { all_tenants: "true" },
      session: { isPlatformAdmin: true } as Record<string, unknown>,
    });
    const next = vi.fn();
    platformAdminMiddleware(req, {} as Response, next);
    expect(req.session.platformAdminView).toBe(true);
    expect(next).toHaveBeenCalled();
  });

  it("sets platformAdminView=false when ?all_tenants=false", () => {
    const req = makeReq({
      query: { all_tenants: "false" },
      session: { isPlatformAdmin: true, platformAdminView: true } as Record<string, unknown>,
    });
    const next = vi.fn();
    platformAdminMiddleware(req, {} as Response, next);
    expect(req.session.platformAdminView).toBe(false);
  });

  it("does not modify session for non-PlatformAdmin operators", () => {
    const req = makeReq({
      query: { all_tenants: "true" },
      session: { isPlatformAdmin: false } as Record<string, unknown>,
    });
    const next = vi.fn();
    platformAdminMiddleware(req, {} as Response, next);
    expect(req.session.platformAdminView).toBeUndefined();
    expect(next).toHaveBeenCalled();
  });

  it("calls next() regardless of outcome", () => {
    const req = makeReq({ session: {} as Record<string, unknown> });
    const next = vi.fn();
    platformAdminMiddleware(req, {} as Response, next);
    expect(next).toHaveBeenCalledOnce();
  });
});
