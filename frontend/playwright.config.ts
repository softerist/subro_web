import { defineConfig, devices } from "@playwright/test";

/**
 * Parse shell-style arguments, respecting quoted strings.
 * e.g., '--flag="value with spaces"' stays as one argument,
 * but the quotes are stripped so Chromium gets '--flag=value with spaces'.
 */
function parseArgs(input: string): string[] {
  const args: string[] = [];
  const regex = /(?:[^\s"]+|"[^"]*")+/g;
  let match;
  while ((match = regex.exec(input)) !== null) {
    // Strip shell-style quotes from values like --flag="value"
    let arg = match[0];
    if (arg.includes('="') && arg.endsWith('"')) {
      arg = arg.replace(/="([^"]*)"$/, "=$1");
    }
    args.push(arg);
  }
  return args;
}

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: "./e2e",
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : undefined,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: "html",
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.E2E_BASE_URL || "http://localhost:8080",

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    ignoreHTTPSErrors: true,
    launchOptions: {
      args: process.env.CHROMIUM_FLAGS
        ? parseArgs(process.env.CHROMIUM_FLAGS)
        : [],
    },
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
