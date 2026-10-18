import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Request, Response } from "express";
import { createLogoutHandler } from "../src/routes/logout.js";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function fakeRes() {
  return { clearCookie: vi.fn(), redirect: vi.fn() } as unknown as Response & {
    clearCookie: ReturnType<typeof vi.fn>;
    redirect: ReturnType<typeof vi.fn>;
  };
}

describe("GET /admin/logout handler", () => {
  beforeEach(() => vi.clearAllMocks());

  it("tells admin-api to log out with the caller's cookie, clears both cookies and redirects to login", async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 204 });
    const res = fakeRes();

    await createLogoutHandler("http://admin-api:8080")({ headers: { cookie: "mintkey_session=abc; csrf_token=def" } } as Request, res);

    expect(mockFetch).toHaveBeenCalledWith("http://admin-api:8080/v1/auth/logout", {
      method: "POST",
      headers: { Cookie: "mintkey_session=abc; csrf_token=def" },
    });
    expect(res.clearCookie).toHaveBeenCalledWith("mintkey_session", { path: "/" });
    expect(res.clearCookie).toHaveBeenCalledWith("csrf_token", { path: "/" });
    expect(res.redirect).toHaveBeenCalledWith(302, "/admin/login");
  });

  it("still clears the cookies and redirects when admin-api is unreachable", async () => {
    mockFetch.mockRejectedValue(new Error("ECONNREFUSED"));
    const res = fakeRes();

    await createLogoutHandler("http://admin-api:8080")({ headers: {} } as Request, res);

    expect(res.clearCookie).toHaveBeenCalledTimes(2);
    expect(res.redirect).toHaveBeenCalledWith(302, "/admin/login");
  });
});
