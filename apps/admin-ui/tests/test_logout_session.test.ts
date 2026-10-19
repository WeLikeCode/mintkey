/**
 * Red tests for the admin-ui logout handler ending the AdminJS session (task 4.2).
 *
 * `createLogoutHandler` must, when a `mintkey_session` cookie is present, call
 * admin-api, destroy `req.session`, clear `adminjs.sid` plus the two operator
 * cookies and redirect to `/admin/login`. A request without either cookie must
 * not call admin-api and must not touch `adminjs.sid`.
 *
 * The app below uses a real `express-session` MemoryStore, so the session is
 * proven gone by a later request with the old `adminjs.sid` cookie.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import express from "express";
import session from "express-session";
import request from "supertest";
import type { Request, Response } from "express";
import { createLogoutHandler } from "../src/routes/logout.js";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const ADMIN_API_URL = "http://admin-api:8080";
const ADMINJS_COOKIE = "adminjs.sid";
const SESSION_COOKIE = "mintkey_session=live-session";
const CSRF_COOKIE = "csrf_token=csrf-value";

type AdminUser = { email: string; csrfToken: string };

function setCookieValues(res: request.Response): string[] {
  const raw = res.headers["set-cookie"] as string[] | string | undefined;
  if (!raw) return [];
  return Array.isArray(raw) ? raw : [raw];
}

function cookieValue(res: request.Response, name: string): string {
  for (const entry of setCookieValues(res)) {
    const pair = entry.split(";")[0];
    const separator = pair.indexOf("=");
    if (separator === -1) continue;
    if (pair.slice(0, separator).trim() !== name) continue;
    return pair.slice(separator + 1).trim();
  }
  throw new Error(`missing ${name} cookie in ${JSON.stringify(setCookieValues(res))}`);
}

function expectCleared(res: request.Response, name: string): void {
  const entries = setCookieValues(res);
  const match = entries.find((entry) => entry.startsWith(`${name}=`));
  expect(match, `expected a Set-Cookie for ${name} in ${JSON.stringify(entries)}`).toBeDefined();
  expect(match!.toLowerCase()).toContain("expires=thu, 01 jan 1970");
  expect(match!).toContain("Path=/");
}

function sessionCount(store: session.MemoryStore): Promise<number> {
  return new Promise((resolve, reject) => {
    store.all((err: unknown, sessions: Record<string, unknown> | null) => {
      if (err) reject(err);
      else resolve(sessions ? Object.keys(sessions).length : 0);
    });
  });
}

function createApp(store: session.Store = new session.MemoryStore()) {
  const app = express();

  app.use(
    session({
      name: ADMINJS_COOKIE,
      secret: "test-secret",
      resave: false,
      saveUninitialized: false,
      store,
      cookie: { secure: false },
    })
  );

  app.get("/test-seed-session", (req, res) => {
    (req.session as unknown as { adminUser?: AdminUser }).adminUser = {
      email: "op@example.test",
      csrfToken: "tok",
    };
    res.status(204).end();
  });

  app.get("/test-session-state", (req, res) => {
    const adminUser = (req.session as unknown as { adminUser?: AdminUser }).adminUser;
    res.status(adminUser ? 200 : 401).json({ adminUser: adminUser ?? null });
  });

  app.post(
    "/admin/logout",
    express.urlencoded({ extended: false }),
    createLogoutHandler(ADMIN_API_URL)
  );

  return { app, store };
}

async function seedSession(app: express.Express): Promise<string> {
  const seeded = await request(app).get("/test-seed-session");
  expect(seeded.status).toBe(204);
  const sid = cookieValue(seeded, ADMINJS_COOKIE);
  return `${ADMINJS_COOKIE}=${sid}`;
}

function operatorCookieHeader(adminjsCookie: string): string {
  return `${adminjsCookie}; ${SESSION_COOKIE}; ${CSRF_COOKIE}`;
}

function fakeRes() {
  return { clearCookie: vi.fn(), redirect: vi.fn() } as unknown as Response & {
    clearCookie: ReturnType<typeof vi.fn>;
    redirect: ReturnType<typeof vi.fn>;
  };
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe("createLogoutHandler — C-a6ef632a a full logout", () => {
  it("C-a6ef632a: calls admin-api, destroys the AdminJS session, clears all three cookies and redirects", async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 204 });
    const { app, store } = createApp();
    const adminjsCookie = await seedSession(app);
    const cookieHeader = operatorCookieHeader(adminjsCookie);

    expect(await sessionCount(store)).toBe(1);

    const res = await request(app).post("/admin/logout").set("Cookie", cookieHeader);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(`${ADMIN_API_URL}/v1/auth/logout`, {
      method: "POST",
      headers: { Cookie: cookieHeader },
    });
    expect(res.status).toBe(302);
    expect(res.headers.location).toBe("/admin/login");
    expectCleared(res, ADMINJS_COOKIE);
    expectCleared(res, "mintkey_session");
    expectCleared(res, "csrf_token");
    expect(await sessionCount(store)).toBe(0);

    const later = await request(app).get("/test-session-state").set("Cookie", adminjsCookie);
    expect(later.status).toBe(401);
    expect(later.body.adminUser).toBeNull();
  });
});

describe("createLogoutHandler — C-5dc3374d admin-api is unreachable or refuses", () => {
  it("C-5dc3374d: destroys the AdminJS session and clears the cookies when fetch rejects", async () => {
    mockFetch.mockRejectedValue(new Error("ECONNREFUSED"));
    const { app, store } = createApp();
    const adminjsCookie = await seedSession(app);

    const res = await request(app)
      .post("/admin/logout")
      .set("Cookie", operatorCookieHeader(adminjsCookie));

    expect(res.status).toBe(302);
    expect(res.headers.location).toBe("/admin/login");
    expectCleared(res, ADMINJS_COOKIE);
    expectCleared(res, "mintkey_session");
    expectCleared(res, "csrf_token");
    expect(await sessionCount(store)).toBe(0);
  });

  it("C-5dc3374d: destroys the AdminJS session and clears the cookies when admin-api answers 503", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 503 });
    const { app, store } = createApp();
    const adminjsCookie = await seedSession(app);

    const res = await request(app)
      .post("/admin/logout")
      .set("Cookie", operatorCookieHeader(adminjsCookie));

    expect(res.status).toBe(302);
    expect(res.headers.location).toBe("/admin/login");
    expectCleared(res, ADMINJS_COOKIE);
    expectCleared(res, "mintkey_session");
    expectCleared(res, "csrf_token");
    expect(await sessionCount(store)).toBe(0);
  });
});

describe("createLogoutHandler — C-a4f02538 the session store fails to destroy", () => {
  it("C-a4f02538: still clears the three cookies and redirects when destroy reports an error", async () => {
    class FailingDestroyStore extends session.MemoryStore {
      destroy(_sid: string, callback: (err?: unknown) => void): void {
        callback(new Error("destroy failed"));
      }
    }

    mockFetch.mockResolvedValue({ ok: true, status: 204 });
    const { app } = createApp(new FailingDestroyStore());
    const adminjsCookie = await seedSession(app);

    const res = await request(app)
      .post("/admin/logout")
      .set("Cookie", operatorCookieHeader(adminjsCookie));

    expect(res.status).toBe(302);
    expect(res.headers.location).toBe("/admin/login");
    expectCleared(res, ADMINJS_COOKIE);
    expectCleared(res, "mintkey_session");
    expectCleared(res, "csrf_token");
  });
});

describe("createLogoutHandler — C-3cb4c380 a request with no session object", () => {
  it("C-3cb4c380: calls no admin-api, clears only the operator cookies and redirects", async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 204 });
    const res = fakeRes();
    const req = { headers: {} } as unknown as Request;

    await createLogoutHandler(ADMIN_API_URL)(req, res);

    expect(mockFetch).not.toHaveBeenCalled();
    expect(res.clearCookie).toHaveBeenCalledTimes(2);
    expect(res.clearCookie).toHaveBeenCalledWith("mintkey_session", { path: "/" });
    expect(res.clearCookie).toHaveBeenCalledWith("csrf_token", { path: "/" });
    expect(res.clearCookie).not.toHaveBeenCalledWith(ADMINJS_COOKIE, { path: "/" });
    expect(res.redirect).toHaveBeenCalledWith(302, "/admin/login");
  });
});

describe("createLogoutHandler — C-e0bc4928 two concurrent logouts", () => {
  it("C-e0bc4928: both redirect, both clear adminjs.sid and the store ends empty", async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 204 });
    const { app, store } = createApp();
    const adminjsCookie = await seedSession(app);
    const cookieHeader = operatorCookieHeader(adminjsCookie);

    const [first, second] = await Promise.all([
      request(app).post("/admin/logout").set("Cookie", cookieHeader),
      request(app).post("/admin/logout").set("Cookie", cookieHeader),
    ]);

    for (const res of [first, second]) {
      expect(res.status).toBe(302);
      expect(res.headers.location).toBe("/admin/login");
      expectCleared(res, ADMINJS_COOKIE);
      expectCleared(res, "mintkey_session");
      expectCleared(res, "csrf_token");
    }
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(await sessionCount(store)).toBe(0);
  });
});
