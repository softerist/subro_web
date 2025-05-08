// frontend/.eslintrc.js or project_root/.eslintrc.js (adjust path if needed)
module.exports = {
  // Indicate that this is the root config file for this directory tree
  root: true,

  // Environment settings: defines global variables available
  env: {
    browser: true, // Browser global variables (like `window`, `document`)
    es2021: true, // Enables ES2021 globals and syntax (like BigInt)
    node: true, // Node.js global variables and Node.js scoping (useful for build scripts, etc. if applicable)
  },

  // Specifies the ESLint parser for TypeScript
  parser: "@typescript-eslint/parser",

  // Parser options: configure how ESLint understands your code
  parserOptions: {
    ecmaVersion: "latest", // Use the latest ECMAScript standard version
    sourceType: "module", // Allow the use of ES Modules (import/export) in your source code
    ecmaFeatures: {
      jsx: true, // Enable parsing of JSX
    },
    // Optional: If you want to use rules that require type information
    // project: "./tsconfig.json", // or an array like ['./tsconfig.json', './tsconfig.node.json']
  },

  // Base configurations to extend
  extends: [
    "eslint:recommended", // ESLint's built-in recommended rules
    "plugin:@typescript-eslint/recommended", // Recommended rules for TypeScript from @typescript-eslint/eslint-plugin
    // "plugin:@typescript-eslint/recommended-requiring-type-checking", // Optional: If you enable `parserOptions.project`
    "plugin:react/recommended", // Recommended rules for React from eslint-plugin-react
    "plugin:react/jsx-runtime", // For new JSX transform (React 17+) - disables rules handled by the transform
    "plugin:react-hooks/recommended", // Recommended rules for React Hooks
    "prettier", // IMPORTANT: Turns off ESLint rules that conflict with Prettier. Must be LAST in extends.
  ],

  // Plugins provide additional rulesets or processors
  plugins: [
    "@typescript-eslint", // @typescript-eslint/eslint-plugin
    "react", // eslint-plugin-react
    "react-hooks", // eslint-plugin-react-hooks
    "react-refresh", // eslint-plugin-react-refresh (for Fast Refresh)
  ],

  // Settings shared across plugins
  settings: {
    react: {
      version: "detect", // Automatically detect the React version being used
    },
  },

  // Custom rule overrides or additions
  rules: {
    "react/prop-types": "off", // Turn off prop-types rule if using TypeScript
    // "react/react-in-jsx-scope": "off", // Already handled by plugin:react/jsx-runtime, but explicit "off" is fine
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true },
    ],
    // You might want to configure unused vars for TypeScript specifically
    "no-unused-vars": "off", // Turn off base no-unused-vars rule
    "@typescript-eslint/no-unused-vars": [ // Use TypeScript-specific rule
      "warn",
      {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        caughtErrorsIgnorePattern: "^_",
      },
    ],
    // Add any other specific rule overrides here
  },

  // Ignore specific files or directories
  ignorePatterns: [
    "node_modules/",
    "build/",
    "dist/",
    ".vite/", // Example: common for Vite projects
    ".eslintcache",
    // Be careful with ".*" as it's very broad.
    // List specific dotfiles/folders if needed, e.g., ".config/"
    "*.config.js", // Ignores vite.config.js, tailwind.config.js etc.
    "*.config.ts", // Ignores vite.config.ts, tailwind.config.ts etc.
    // If this eslintrc file itself is in the root of what's being linted and named .eslintrc.js,
    // you might need to explicitly list it if other patterns could catch it.
    // However, ESLint usually doesn't lint its own config by default.
  ],
};
