import { defineProject } from "vitest/config";

// Node-env project: all existing .ts tests.
// No aliases — uses the real adminjs package.
export default defineProject({
  test: {
    name: "node-tests",
    globals: true,
    environment: "node",
    include: ["tests/**/*.test.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
