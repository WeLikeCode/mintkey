import { defineWorkspace } from "vitest/config";

export default defineWorkspace([
  // Project 1: existing node-env tests (unchanged)
  "./vitest.node.config.ts",
  // Project 2: jsdom render tests with stubs for adminjs design-system deps
  "./vitest.render.config.ts",
]);
