// ESLint flat config for the web app (refactor step C2).
//   npm run lint
// typescript-eslint recommended, the two classic react-hooks rules, and jsx-a11y recommended as errors (step E4; C2
// had them as warnings).
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
// @ts-expect-error -- the plugin ships no type declarations (tsconfig.node.json checks this file)
import jsxA11y from "eslint-plugin-jsx-a11y";
import checkFile from "eslint-plugin-check-file";
import globals from "globals";

export default tseslint.config(
  { ignores: ["dist/", "node_modules/", "src/assets/assets.gen.ts"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    linterOptions: { reportUnusedDisableDirectives: "error" },
    rules: {
      // a leading underscore marks a parameter or binding kept on purpose (positional ports of the legacy helpers,
      // rest-destructuring that drops a field)
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          destructuredArrayIgnorePattern: "^_",
        },
      ],
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  {
    // the plugin's recommended set as it ships: its rules are errors, and the few it leaves off stay off
    files: ["**/*.tsx"],
    ...jsxA11y.flatConfigs.recommended,
  },
  {
    // node scripts (asset extraction, golden dumps, smoke tests) and config files run under node
    files: ["scripts/**/*.{js,mjs}", "*.config.{js,ts}"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // smoke scripts pass callbacks to page.evaluate(), which run in the browser
    files: ["scripts/**/*.mjs"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    // file names (refactor step B3): components PascalCase.tsx, other modules camelCase.ts, folders kebab-case.
    // A test file is checked on the part before ".test" (ignoreMiddleExtensions), so it follows its subject.
    files: ["**/*.{ts,tsx}"],
    ignores: [
      "**/index.tsx", // an area's page map, found by name by src/pages/registry.tsx
      "**/main.tsx",
      "**/*.gen.ts",
      "**/vite.config.ts",
      // accepted exceptions (decision log, 2026-11-20, B3)
      "src/components/toast.tsx",
      "src/utils/theme.ts",
      "src/utils/askBus.ts",
      "src/pages/registry.tsx", // the route table (a module, not a component)
    ],
    plugins: { "check-file": checkFile },
    rules: {
      "check-file/filename-naming-convention": [
        "error",
        { "**/*.tsx": "PASCAL_CASE", "**/*.ts": "CAMEL_CASE" },
        { ignoreMiddleExtensions: true },
      ],
      "check-file/folder-naming-convention": ["error", { "src/**/": "KEBAB_CASE" }],
    },
  },
);
