import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@duckyai/shared": path.resolve(__dirname, "../shared/src/index.ts"),
      obsidian: path.resolve(__dirname, "src/__tests__/mocks/obsidian.ts"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["../shared/src/__tests__/setup.ts"],
    include: ["src/__tests__/**/*.test.{ts,tsx}"],
  },
});
