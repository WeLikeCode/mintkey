// This file is kept as a fallback for tools that expect vitest.config.ts.
// The actual configuration is split into two workspace projects:
//   - vitest.node.config.ts  — node environment (existing .ts tests)
//   - vitest.render.config.ts — jsdom environment (.tsx render tests)
// The workspace is declared in vitest.workspace.ts.
//
// If you need to run ALL tests: `pnpm vitest run` (picks up vitest.workspace.ts).
// If you need to run only render tests: `pnpm vitest run --project render-tests`.
// If you need to run only node tests:   `pnpm vitest run --project node-tests`.

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["tests/**/*.test.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
