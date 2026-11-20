// Flat config: type-aware ESLint on src/; lighter rules on e2e and tooling. Prettier owns formatting.
import js from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "test-results", "playwright-report", "coverage"] },
  js.configs.recommended,
  {
    files: ["e2e/**/*.{ts,mjs}", "*.config.{js,ts}", "vitest.config.ts"],
    extends: [...tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.node },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [
      ...tseslint.configs.recommendedTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
      jsxA11y.flatConfigs.recommended,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/consistent-type-definitions": "off", // API types use `type` for unions and aliases
      "@typescript-eslint/prefer-nullish-coalescing": "off", // existing || matches API optional fields
      "@typescript-eslint/prefer-optional-chain": "off",
      "@typescript-eslint/no-base-to-string": "off", // React Flow data bags are loosely typed
      "@typescript-eslint/no-redundant-type-constituents": "off",
      "@typescript-eslint/consistent-type-imports": ["error", { disallowTypeAnnotations: false }],
      "@typescript-eslint/no-misused-promises": ["error", { checksVoidReturn: { attributes: false } }],
      // React Flow canvas and custom graph chrome; axe E2E still runs on real screens.
      "jsx-a11y/no-static-element-interactions": "off",
      "jsx-a11y/no-noninteractive-tabindex": "off",
      "jsx-a11y/no-autofocus": "off",
      "jsx-a11y/no-noninteractive-element-interactions": "off",
      eqeqeq: "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
  eslintConfigPrettier,
);
