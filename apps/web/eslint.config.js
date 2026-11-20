// ESLint flat config for the web app (refactor step C2).
//   npm run lint
// typescript-eslint recommended, the two classic react-hooks rules, and jsx-a11y recommended. The a11y rules are
// warnings for now so this step lands without markup rewrites; step E4 fixes them and turns them into errors.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import checkFile from "eslint-plugin-check-file";
import globals from "globals";

const a11yAsWarnings = Object.fromEntries(
  Object.entries(jsxA11y.flatConfigs.recommended.rules).map(([rule, setting]) => [
    rule,
    Array.isArray(setting) ? ["warn", ...setting.slice(1)] : setting === "off" || setting === 0 ? setting : "warn",
  ]),
);

export default tseslint.config(
  { ignores: ["dist/", "node_modules/", "src/ui/assets.gen.ts"] },
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
    files: ["**/*.tsx"],
    ...jsxA11y.flatConfigs.recommended,
    rules: a11yAsWarnings,
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
      "src/ui/toast.tsx",
      "src/ui/theme.ts",
      "src/ui/askBus.ts",
      "src/pages/registry.tsx", // the route table (a module, not a component)
      // split into src/ui/kit/* and area files by "Naming B" (step E2); drop them from this list then
      "src/pages/home/kit.tsx",
      "src/pages/workflows/kit.tsx",
      "src/pages/case/kit.tsx",
      "src/pages/case/ui.tsx",
      "src/pages/integration/ui.tsx",
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
