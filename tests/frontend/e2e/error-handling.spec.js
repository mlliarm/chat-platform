import { expect, test } from "@playwright/test";
import { mockChatError } from "./helpers/mockApi.js";

test("shows a friendly banner instead of the raw error when a model can't see images", async ({ page }) => {
  await mockChatError(page, { error: "No endpoints found that support image input" });
  await page.goto("/");

  await page.locator("#prompt-input").fill("describe this");
  await page.locator("#send-btn").click();

  const banner = page.locator(".error-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("vision-capable model");
  await expect(banner).not.toContainText("No endpoints found");
  // The empty assistant placeholder bubble is removed on failure.
  await expect(page.locator(".message-row.assistant")).toHaveCount(0);
});
