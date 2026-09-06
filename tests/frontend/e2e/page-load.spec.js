import { expect, test } from "@playwright/test";

test("loads the app with an empty state and default model", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator(".empty-state h1")).toHaveText("What can I help with?");
  await expect(page.locator("#chat-list")).toBeEmpty();
  await expect(page.locator("#export-pdf-btn")).toBeDisabled();
});
