import { expect, test } from "@playwright/test";
import { installFakeChatBackend } from "./helpers/mockApi.js";

test("Enter sends the message", async ({ page }) => {
  await installFakeChatBackend(page);
  await page.goto("/");

  await page.locator("#prompt-input").fill("sent with enter");
  await page.locator("#prompt-input").press("Enter");

  await expect(page.locator(".message-row.user .message-content")).toHaveText("sent with enter");
});

test("Shift+Enter inserts a newline instead of sending", async ({ page }) => {
  await installFakeChatBackend(page);
  await page.goto("/");

  const input = page.locator("#prompt-input");
  await input.fill("line one");
  await input.press("Shift+Enter");
  await input.type("line two");

  await expect(input).toHaveValue("line one\nline two");
  await expect(page.locator(".message-row")).toHaveCount(0);
});
