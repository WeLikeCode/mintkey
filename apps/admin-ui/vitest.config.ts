// Vitest configuration with two projects (Vitest 4+).
//
//   - node-tests   — node environment, existing .ts tests, real adminjs package.
//   - render-tests — jsdom environment, .render.test.tsx tests, with aliases that
//                    stub out @adminjs/design-system, adminjs, and react-router-dom
//                    so components render without the full AdminJS peer dep tree.
//
// Vitest 4 removed `defineWorkspace` and the external `vitest.workspace.ts`
// mechanism; projects are now declared inline via `test.projects`.
//
// Run ALL tests:        `pnpm vitest run`
// Run only render tests: `pnpm vitest run --project render-tests`
// Run only node tests:   `pnpm vitest run --project node-tests`

import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    projects: [
      {
        test: {
          name: "node-tests",
          globals: true,
          environment: "node",
          include: ["tests/**/*.test.ts"],
          exclude: ["e2e/**", "node_modules/**"],
        },
      },
      {
        resolve: {
          alias: {
            "@adminjs/design-system": path.resolve(
              __dirname,
              "tests/__mocks__/adminjs-design-system.tsx"
            ),
            adminjs: path.resolve(__dirname, "tests/__mocks__/adminjs-stub.ts"),
            "react-router-dom": path.resolve(
              __dirname,
              "tests/__mocks__/react-router-dom-stub.ts"
            ),
          },
        },
        test: {
          name: "render-tests",
          globals: true,
          environment: "jsdom",
          include: ["tests/**/*.render.test.tsx"],
          exclude: ["e2e/**", "node_modules/**"],
        },
      },
    ],
  },
});
