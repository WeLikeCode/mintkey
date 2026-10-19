/**
 * Red tests for the admin-ui logout router (task 4.3).
 *
 * `renderLogoutPage`, `logoutPageHandler` and `createLogoutRouter` are added to
 * `src/routes/logout.ts` in the green step. Until then the module has no such
 * exports; the helper below asserts that the symbol exists before it is called,
 * so the red run fails with a Vitest assertion (not a TypeError for a missing
 * function).
 *
 * The app mounts the real router behind a real `express-session` MemoryStore so
 * the GET page, the CSRF guard and the POST handler are exercised together.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import express, {
  type Request,
  type RequestHandler,
  type Response,
  type Router,
} from "express";
import session from "express-session";
import request from "supertest";
import * as logoutModule from "../src/routes/logout.js";

type CreateLogoutRouter = (adminApiUrl: string, rateLimiter: RequestHandler) => Router;

const mod = logoutModule as typeof logoutModule & {
  createLogoutRouter?: CreateLogoutRouter;
};

const ADMIN_API_URL = "http://admin-api:8080";
const ADMINJS_COOKIE = "adminjs.sid";
const SESSION_COOKIE = "mintkey_session=live-session";
const CSRF_VALUE = 'a"b&c<d>e';
const CSRF_ESCAPED = "a&quot;b&amp;c&lt;d&gt;e";
const CSRF_COOKIE = `csrf_token=${CSRF_VALUE}`;

type AdminUser = { email: string; csrfToken: string };

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function createLogoutRouter(adminApiUrl: string, rateLimiter: RequestHandler): Router {
  expect(typeof mod.createLogoutRouter).toBe("function");
  return (mod.createLogoutRouter as CreateLogoutRouter)(adminApiUrl, rateLimiter);
}

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

function expectNoCookiesSet(res: request.Response): void {
  expect(res.headers["set-cookie"]).toBeUndefined();
}

function createApp(limiter: RequestHandler) {
  const app = express();
  const store = new session.MemoryStore();

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

  app.use(createLogoutRouter(ADMIN_API_URL, limiter));

  return { app, store };
}

async function seedSession(app: express.Express): Promise<string> {
  const seeded = await request(app).get("/test-seed-session");
  expect(seeded.status).toBe(204);
  return `${ADMINJS_COOKIE}=${cookieValue(seeded, ADMINJS_COOKIE)}`;
}

function countingLimiter() {
  const calls: string[] = [];
  const middleware: RequestHandler = (req, _res, next) => {
    calls.push(`${req.method} ${req.path}`);
    next();
  };
  return { middleware, calls };
}

function tagWith(html: string, name: string): string {
  const tags = html.match(/<(?:form|input|button)\b[^>]*>/gi) ?? [];
  const tag = tags.find((candidate) => candidate.includes(name));
  expect(tag, `expected a tag containing ${name} in ${html}`).toBeDefined();
  return tag as string;
}

function attribute(tag: string, name: string): string | undefined {
  const match = tag.match(new RegExp(`${name}\\s*=\\s*"([^"]*)"`, "i"));
  return match?.[1];
}

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue({ ok: true, status: 204 });
});

describe("GET /admin/logout — C-4749db35 renders a confirmation form", () => {
  it("C-4749db35: renders an escaped _csrf form without side effects", async () => {
    const { middleware } = countingLimiter();
    const { app } = createApp(middleware);
    const adminjsCookie = await seedSession(app);

    const res = await request(app)
      .get("/admin/logout")
      .set("Cookie", `${adminjsCookie}; ${SESSION_COOKIE}; ${CSRF_COOKIE}`);

    expect(res.status).toBe(200);
    expect(String(res.headers["content-type"])).toMatch(/^text\/html/);
    expect(String(res.headers["cache-control"])).toContain("no-store");

    const html = res.text;
    const form = tagWith(html, "<form");
    expect(attribute(form, "method")).toMatch(/^post$/i);
    expect(attribute(form, "action")).toBe("/admin/logout");

    const csrf = tagWith(html, 'name="_csrf"');
    expect(attribute(csrf, "type")).toBe("hidden");
    expect(attribute(csrf, "value")).toBe(CSRF_ESCAPED);

    const button = tagWith(html, 'data-testid="logout-confirm"');
    expect(attribute(button, "type")).toMatch(/^submit$/i);

    expect(html).not.toMatch(/<script/i);
    expect(mockFetch).not.toHaveBeenCalled();
    expectNoCookiesSet(res);

    const later = await request(app)
      .get("/test-session-state")
      .set("Cookie", adminjsCookie);
    expect(later.status).toBe(200);
    expect(later.body.adminUser.email).toBe("op@example.test");
  });
});

describe("GET /admin/logout — C-12db9b82 without a CSRF cookie", () => {
  it("C-12db9b82: renders the same form with an empty _csrf value and changes nothing", async () => {
    const { middleware } = countingLimiter();
    const { app } = createApp(middleware);
    const adminjsCookie = await seedSession(app);

    const res = await request(app)
      .get("/admin/logout")
      .set("Cookie", `${adminjsCookie}; ${SESSION_COOKIE}`);

    expect(res.status).toBe(200);
    const form = tagWith(res.text, "<form");
    expect(attribute(form, "method")).toMatch(/^post$/i);
    expect(attribute(form, "action")).toBe("/admin/logout");

    const csrf = tagWith(res.text, 'name="_csrf"');
    expect(attribute(csrf, "value")).toBe("");
    tagWith(res.text, 'data-testid="logout-confirm"');

    expect(mockFetch).not.toHaveBeenCalled();
    expectNoCookiesSet(res);

    const refused = await request(app)
      .post("/admin/logout")
      .set("Cookie", `${adminjsCookie}; ${SESSION_COOKIE}`)
      .type("form")
      .send({ _csrf: "" });
    expect(refused.status).toBe(403);
    expect(refused.text).toBe("Logout refused: missing or invalid CSRF token");
    expectNoCookiesSet(refused);

    const later = await request(app)
      .get("/test-session-state")
      .set("Cookie", adminjsCookie);
    expect(later.status).toBe(200);
    expect(later.body.adminUser.email).toBe("op@example.test");
  });
});

describe("GET /admin/logout — C-f7e06575 without a session", () => {
  it("C-f7e06575: redirects to /admin/login when there is no session", async () => {
    const { middleware } = countingLimiter();
    const { app } = createApp(middleware);

    const res = await request(app).get("/admin/logout");

    expect(res.status).toBe(302);
    expect(res.headers.location).toBe("/admin/login");
    expect(mockFetch).not.toHaveBeenCalled();
    expectNoCookiesSet(res);
  });
});

describe("createLogoutRouter — C-6a1cff5f serves both methods behind the limiter", () => {
  it("C-6a1cff5f: the limiter runs for GET and both POSTs, and each answer is right", async () => {
    const { middleware, calls } = countingLimiter();
    const { app, store } = createApp(middleware);
    const adminjsCookie = await seedSession(app);
    const pageCookie = `${adminjsCookie}; ${SESSION_COOKIE}; ${CSRF_COOKIE}`;

    const page = await request(app).get("/admin/logout").set("Cookie", pageCookie);
    expect(page.status).toBe(200);
    tagWith(page.text, "<form");
    tagWith(page.text, 'name="_csrf"');
    tagWith(page.text, 'data-testid="logout-confirm"');

    const refused = await request(app)
      .post("/admin/logout")
      .set("Cookie", pageCookie)
      .type("form")
      .send({});
    expect(refused.status).toBe(403);
    expect(refused.text).toBe("Logout refused: missing or invalid CSRF token");

    const accepted = await request(app)
      .post("/admin/logout")
      .set("Cookie", pageCookie)
      .type("form")
      .send({ _csrf: CSRF_VALUE });
    expect(accepted.status).toBe(302);
    expect(accepted.headers.location).toBe("/admin/login");
    expectCleared(accepted, ADMINJS_COOKIE);
    expectCleared(accepted, "mintkey_session");
    expectCleared(accepted, "csrf_token");
    expect(mockFetch).toHaveBeenCalledTimes(1);

    expect(calls).toHaveLength(3);
    expect(calls[0]).toBe("GET /admin/logout");
    expect(calls[1]).toBe("POST /admin/logout");
    expect(calls[2]).toBe("POST /admin/logout");

    const count = await new Promise<number>((resolve, reject) => {
      store.all((err: unknown, sessions: Record<string, unknown> | null) => {
        if (err) reject(err);
        else resolve(sessions ? Object.keys(sessions).length : 0);
      });
    });
    expect(count).toBe(0);
  });
});
