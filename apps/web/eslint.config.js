// ESLint flat config for the web app (refactor step C2).
//   npm run lint
// typescript-eslint recommended, the two classic react-hooks rules, and jsx-a11y recommended. The a11y rules are
// warnings for now so this step lands without markup rewrites; step E4 fixes them and turns them into errors.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
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
    files: ["scripts/**/*.{js,mjs}", "e2e/**/*.{js,mjs,ts}", "*.config.{js,ts}"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // smoke scripts pass callbacks to page.evaluate(), which run in the browser
    files: ["scripts/**/*.mjs", "e2e/**/*.{js,mjs,ts}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
);
