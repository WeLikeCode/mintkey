import { defineProject } from "vitest/config";
import path from "path";

// jsdom render project: .tsx render tests only.
// Resolve aliases stub out @adminjs/design-system, adminjs, and react-router-dom
// so the component can be rendered without the full AdminJS peer dep tree.
export default defineProject({
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
});
