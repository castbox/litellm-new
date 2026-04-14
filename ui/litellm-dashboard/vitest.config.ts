import { defineConfig } from "vitest/config";
import { resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["tests/setupTests.ts"],
    globals: true,
    css: true, // lets you import CSS/modules without extra mocks
    coverage: { reporter: ["text", "lcov"] },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  define: {
    "import.meta.vitest": "undefined",
  },
  esbuild: {
    jsx: "automatic",
    jsxImportSource: "react",
  },
});
