/**
 * Red tests for the admin-ui logout CSRF guard (task 4.1).
 *
 * `readCookie` and `logoutGuard` are added to `src/routes/logout.ts` in the green step. Until then the
 * module has no such exports; the helpers below assert that each symbol exists before calling it, so the
 * red run fails with a Vitest assertion (not a TypeError for a missing function).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { NextFunction, Request, Response } from "express";
import * as logoutModule from "../src/routes/logout.js";

type ReadCookie = (header: string | undefined, name: string) => string | undefined;
type LogoutGuard = (req: Request, res: Response, next: NextFunction) => void;

const mod = logoutModule as typeof logoutModule & {
  readCookie?: ReadCookie;
  logoutGuard?: LogoutGuard;
};

const REFUSED_BODY = "Logout refused: missing or invalid CSRF token";

function readCookie(header: string | undefined, name: string): string | undefined {
  expect(typeof mod.readCookie).toBe("function");
  return (mod.readCookie as ReadCookie)(header, name);
}

function logoutGuard(req: Request, res: Response, next: NextFunction): void {
  expect(typeof mod.logoutGuard).toBe("function");
  (mod.logoutGuard as LogoutGuard)(req, res, next);
}

type FakeResponse = Response & {
  statusCode: number;
  body: unknown;
  redirectStatus?: number;
  redirectUrl?: string;
  headers: Record<string, string | string[]>;
  status: ReturnType<typeof vi.fn>;
  setHeader: ReturnType<typeof vi.fn>;
  send: ReturnType<typeof vi.fn>;
  redirect: ReturnType<typeof vi.fn>;
  clearCookie: ReturnType<typeof vi.fn>;
};

function fakeRes(): FakeResponse {
  const headers: Record<string, string | string[]> = {};
  const res = {
    statusCode: 200,
    body: undefined as unknown,
    redirectStatus: undefined as number | undefined,
    redirectUrl: undefined as string | undefined,
    headers,
    status(code: number) {
      res.statusCode = code;
      return res;
    },
    setHeader(name: string, value: string | string[]) {
      headers[name.toLowerCase()] = value;
      return res;
    },
    set(name: string, value: string | string[]) {
      return res.setHeader(name, value);
    },
    header(name: string, value: string | string[]) {
      return res.setHeader(name, value);
    },
    type(value: string) {
      return res.setHeader("content-type", value);
    },
    contentType(value: string) {
      return res.setHeader("content-type", value);
    },
    send(body: unknown) {
      res.body = body;
      return res;
    },
    redirect(statusOrUrl: number | string, maybeUrl?: string) {
      if (typeof statusOrUrl === "number") {
        res.redirectStatus = statusOrUrl;
        res.redirectUrl = maybeUrl;
      } else {
        res.redirectStatus = 302;
        res.redirectUrl = statusOrUrl;
      }
      return res;
    },
    clearCookie: vi.fn(),
  };
  return res as unknown as FakeResponse;
}

function fakeReq(options: {
  cookie?: string;
  csrf?: string;
  adminUser?: { email: string } | null;
  noSession?: boolean;
}): Request {
  const headers: Record<string, string> = {};
  if (options.cookie !== undefined) headers.cookie = options.cookie;

  const body: Record<string, unknown> = {};
  if (options.csrf !== undefined) body._csrf = options.csrf;

  const req: Record<string, unknown> = { headers, body };
  if (!options.noSession) {
    req.session = { adminUser: options.adminUser ?? undefined };
  }
  return req as unknown as Request;
}

function expectNoCookiesSet(res: FakeResponse): void {
  expect(res.clearCookie).not.toHaveBeenCalled();
  expect(res.headers["set-cookie"]).toBeUndefined();
}

function expectRefused(res: FakeResponse, next: ReturnType<typeof vi.fn>): void {
  expect(next).not.toHaveBeenCalled();
  expect(res.statusCode).toBe(403);
  expect(String(res.body)).toBe(REFUSED_BODY);
  expect(String(res.headers["content-type"] ?? "")).toMatch(/^text\/plain/);
  expectNoCookiesSet(res);
}

describe("readCookie", () => {
  beforeEach(() => vi.clearAllMocks());

  it("C-f475d740: matches the exact cookie name (xcsrf_token is not csrf_token)", () => {
    expect(readCookie("xcsrf_token=a; csrf_token=b", "csrf_token")).toBe("b");
    expect(readCookie("xcsrf_token=a", "csrf_token")).toBeUndefined();
  });

  it("C-de8201d5: keeps every '=' after the first one in the value", () => {
    expect(readCookie("a=b=c", "a")).toBe("b=c");
    expect(readCookie("token=abc=def=ghi; other=x", "token")).toBe("abc=def=ghi");
  });

  it("C-de8201d5: does not percent-decode the value", () => {
    expect(readCookie("a=%2F%3D", "a")).toBe("%2F%3D");
  });

  it("C-de8201d5: returns the first occurrence of a repeated name", () => {
    expect(readCookie("a=first; a=second", "a")).toBe("first");
  });

  it("C-de8201d5: trims surrounding spaces from the value", () => {
    expect(readCookie("  a =  b  ; c = d ", "a")).toBe("b");
  });

  it("C-f475d740: returns undefined for a missing header, missing name or empty value", () => {
    expect(readCookie(undefined, "a")).toBeUndefined();
    expect(readCookie("", "a")).toBeUndefined();
    expect(readCookie("b=c", "a")).toBeUndefined();
    expect(readCookie("a=; b=c", "a")).toBeUndefined();
    expect(readCookie("a=   ; b=c", "a")).toBeUndefined();
  });
});

describe("logoutGuard — C-f475d740 missing token", () => {
  beforeEach(() => vi.clearAllMocks());

  it("C-f475d740: refuses a request without the _csrf field", () => {
    const req = fakeReq({
      cookie: "mintkey_session=live; csrf_token=cookie-token",
      adminUser: { email: "op@example.test" },
    });
    const res = fakeRes();
    const next = vi.fn();

    logoutGuard(req, res, next as unknown as NextFunction);

    expectRefused(res, next);
  });

  it("C-f475d740: refuses a request without the csrf_token cookie", () => {
    const req = fakeReq({
      cookie: "mintkey_session=live",
      csrf: "form-token",
      adminUser: { email: "op@example.test" },
    });
    const res = fakeRes();
    const next = vi.fn();

    logoutGuard(req, res, next as unknown as NextFunction);

    expectRefused(res, next);
  });
});

describe("logoutGuard — C-de8201d5 wrong token", () => {
  beforeEach(() => vi.clearAllMocks());

  it("C-de8201d5: refuses a token of the same length that differs", () => {
    const req = fakeReq({
      cookie: "mintkey_session=live; csrf_token=abcdef",
      csrf: "abcdeg",
      adminUser: { email: "op@example.test" },
    });
    const res = fakeRes();
    const next = vi.fn();

    logoutGuard(req, res, next as unknown as NextFunction);

    expectRefused(res, next);
  });

  it("C-de8201d5: refuses a token of another length", () => {
    const req = fakeReq({
      cookie: "mintkey_session=live; csrf_token=abcdef",
      csrf: "abc",
      adminUser: { email: "op@example.test" },
    });
    const res = fakeRes();
    const next = vi.fn();

    logoutGuard(req, res, next as unknown as NextFunction);

    expectRefused(res, next);
  });
});

describe("logoutGuard — C-e629437b nothing to log out", () => {
  beforeEach(() => vi.clearAllMocks());

  it("C-e629437b: redirects to login when the session has no adminUser and there is no cookie", () => {
    const req = fakeReq({ adminUser: null });
    const res = fakeRes();
    const next = vi.fn();

    logoutGuard(req, res, next as unknown as NextFunction);

    expect(next).not.toHaveBeenCalled();
    expect(res.redirectStatus).toBe(302);
    expect(res.redirectUrl).toBe("/admin/login");
    expectNoCookiesSet(res);
  });

  it("C-e629437b: redirects to login when there is no session object and no cookie", () => {
    const req = fakeReq({ noSession: true });
    const res = fakeRes();
    const next = vi.fn();

    logoutGuard(req, res, next as unknown as NextFunction);

    expect(next).not.toHaveBeenCalled();
    expect(res.redirectStatus).toBe(302);
    expect(res.redirectUrl).toBe("/admin/login");
    expectNoCookiesSet(res);
  });
});

describe("logoutGuard — valid token", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls next() once when _csrf equals the csrf_token cookie", () => {
    const req = fakeReq({
      cookie: "mintkey_session=live; csrf_token=abcdef",
      csrf: "abcdef",
      adminUser: { email: "op@example.test" },
    });
    const res = fakeRes();
    const next = vi.fn();

    logoutGuard(req, res, next as unknown as NextFunction);

    expect(next).toHaveBeenCalledTimes(1);
    expect(res.redirectUrl).toBeUndefined();
    expectNoCookiesSet(res);
  });
});
