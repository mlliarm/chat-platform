import { expect, test } from "@playwright/test";
import { installFakeChatBackend } from "./helpers/mockApi.js";

test("sends a message and renders the streamed reply, adding the chat to the sidebar", async ({ page }) => {
  await installFakeChatBackend(page, { replyChunks: ["Hello ", "from the model!"] });
  await page.goto("/");

  await page.locator("#prompt-input").fill("hi there, model");
  await page.locator("#send-btn").click();

  await expect(page.locator(".message-row.user .message-content")).toHaveText("hi there, model");
  await expect(page.locator(".message-row.assistant .message-content")).toContainText("Hello from the model!");
  await expect(page.locator(".chat-item .title")).toHaveText("hi there, model");
  await expect(page.locator("#export-pdf-btn")).toBeEnabled();
});
