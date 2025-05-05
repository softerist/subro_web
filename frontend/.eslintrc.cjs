module.exports = {
  // Indicate that this is the root config file for this directory tree
  root: true,

  // Environment settings: defines global variables available
  env: {
    browser: true, // Browser global variables (like `window`, `document`)
    es2021: true, // Enables ES2021 globals and syntax (like BigInt)
    node: true, // Node.js global variables and Node.js scoping (useful for build scripts, etc. if applicable)
  },

  // Base configurations to extend
  extends: [
    "eslint:recommended", // ESLint's built-in recommended rules
    "plugin:react/recommended", // Recommended rules for React from eslint-plugin-react
    "plugin:react/jsx-runtime", // Optional: If using new JSX transform (React 17+) - disables rules handled by the transform
    "plugin:react-hooks/recommended", // Recommended rules for React Hooks
    "prettier", // IMPORTANT: Turns off ESLint rules that conflict with Prettier. Must be LAST in extends.
  ],

  // Parser options: configure how ESLint understands your code
  parserOptions: {
    ecmaVersion: "latest", // Use the latest ECMAScript standard version
    sourceType: "module", // Allow the use of ES Modules (import/export) in your source code
    ecmaFeatures: {
      jsx: true, // Enable parsing of JSX
    },
  },

  // Settings shared across plugins
  settings: {
    react: {
      version: "detect", // Automatically detect the React version being used
    },
  },

  // Plugins provide additional rulesets or processors
  plugins: [
    "react", // eslint-plugin-react
    "react-hooks", // eslint-plugin-react-hooks
    "react-refresh", // eslint-plugin-react-refresh (for Fast Refresh)
    // No need to list 'prettier' here; it's handled by eslint-config-prettier in extends
  ],

  // Custom rule overrides or additions
  rules: {
    // Example rules (adjust as needed):
    "react/prop-types": "off", // Turn off prop-types rule if using TypeScript or prefer not to use them
    "react/react-in-jsx-scope": "off", // Turn off if using new JSX transform (React 17+)
    "react-refresh/only-export-components": [
      // Rule for react-refresh
      "warn",
      { allowConstantExport: true },
    ],
    // Add any other specific rule overrides here
    // e.g., "no-unused-vars": "warn"
  },

  // Ignore specific files or directories
  ignorePatterns: [
    "node_modules/",
    "build/",
    "dist/",
    ".*", // Ignore dotfiles/dotfolders in the frontend directory by default
    "*.config.js", // Ignore config files like vite.config.js, tailwind.config.js etc.
    "*.config.ts",
  ],
};
