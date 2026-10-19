/**
 * Red tests for the admin-ui logout wiring.
 *
 * Task 5.1 registers the `LoggedIn` override in `src/components/index.ts`.
 * `src/index.ts` itself starts the server on import, so its wiring is checked by
 * reading the source, as `test_index_security_config.test.ts` does.
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

describe("components/index.ts — C-7ab935e2 LoggedIn override registration", () => {
  it("C-7ab935e2: registers the LoggedIn override with ./app/LoggedIn", () => {
    expect(componentsSrc).toMatch(
      /componentLoader\.override\(\s*"LoggedIn"\s*,\s*"\.\/app\/LoggedIn"\s*\)/
    );
  });
});
