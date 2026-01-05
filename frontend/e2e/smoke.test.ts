import { test, expect } from "@playwright/test";

test("has title", async ({ page }) => {
  await page.goto("/");

  // Expect a title to contain a substring.
  // Adjust this according to your app's actual title!
  await expect(page).toHaveTitle(/Subro/i);
});

test("api health check", async ({ page }) => {
  const response = await page.goto("/health");
  if (response) {
    expect(response.status()).toBe(200);
    const text = await response.text();
    expect(text).toContain("healthy");
  }
});
