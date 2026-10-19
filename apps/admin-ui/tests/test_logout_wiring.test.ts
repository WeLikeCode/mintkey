/**
 * Red tests for the admin-ui logout wiring.
 *
 * Task 5.1 registers the `LoggedIn` override in `src/components/index.ts`;
 * task 5.2 mounts `createLogoutRouter` in `src/index.ts`. `src/index.ts` itself
 * starts the server on import, so its wiring is checked by reading the source,
 * as `test_index_security_config.test.ts` does.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join, dirname } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const componentsSrc = readFileSync(
  join(__dirname, "../src/components/index.ts"),
  "utf-8"
);
const indexSrc = readFileSync(join(__dirname, "../src/index.ts"), "utf-8");

describe("components/index.ts — C-7ab935e2 LoggedIn override registration", () => {
  it("C-7ab935e2: registers the LoggedIn override with ./app/LoggedIn", () => {
    expect(componentsSrc).toMatch(
      /componentLoader\.override\(\s*"LoggedIn"\s*,\s*"\.\/app\/LoggedIn"\s*\)/
    );
  });
});

describe("src/index.ts — C-234b2839 mounts the logout router", () => {
  it("C-234b2839: mounts createLogoutRouter before requireSession and keeps no GET logout handler", () => {
    expect(indexSrc).toMatch(
      /import\s*\{[^}]*\bcreateLogoutRouter\b[^}]*\}\s*from\s*"\.\/routes\/logout\.js"/
    );

    const mount = indexSrc.search(
      /createLogoutRouter\s*\(\s*ADMIN_API_URL\s*,\s*logoutRateLimit\s*\)/
    );
    expect(mount, "createLogoutRouter(ADMIN_API_URL, logoutRateLimit) must be called").toBeGreaterThanOrEqual(
      0
    );

    const requireSessionMount = indexSrc.search(/app\.use\(\s*requireSession\s*\)/);
    expect(requireSessionMount, "app.use(requireSession) must still be mounted").toBeGreaterThanOrEqual(
      0
    );
    expect(mount).toBeLessThan(requireSessionMount);

    expect(indexSrc).not.toMatch(/app\.get\(\s*"\/admin\/logout"/);
    expect(indexSrc).not.toMatch(/createLogoutHandler/);
  });
});
