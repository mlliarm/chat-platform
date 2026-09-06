import { expect, test } from "@playwright/test";
import { installFakeChatBackend } from "./helpers/mockApi.js";

test("create two chats, switch between them, pin one, and delete one", async ({ page }) => {
  await installFakeChatBackend(page);
  await page.goto("/");

  await page.locator("#prompt-input").fill("first chat message");
  await page.locator("#send-btn").click();
  await expect(page.locator(".chat-item")).toHaveCount(1);

  await page.locator("#new-chat-btn").click();
  await expect(page.locator(".empty-state")).toBeVisible();

  await page.locator("#prompt-input").fill("second chat message");
  await page.locator("#send-btn").click();
  await expect(page.locator(".chat-item")).toHaveCount(2);

  // Switch back to the first chat.
  await page.locator(".chat-item", { hasText: "first chat message" }).click();
  await expect(page.locator(".message-row.user .message-content")).toHaveText("first chat message");

  // Pin the first chat and confirm it persists across a reload (the fake
  // backend's GET /api/chats reflects the pinned flag, same as the real API).
  await page.locator(".chat-item", { hasText: "first chat message" }).locator(".pin-btn").click();
  await page.reload();
  await expect(page.locator(".chat-item").first()).toContainText("first chat message");
  await expect(page.locator(".chat-item").first().locator(".pin-btn")).toHaveClass(/pinned/);

  // The delete button is only visible on hover (visibility:hidden by
  // default), same as for a real user.
  const secondChatItem = page.locator(".chat-item", { hasText: "second chat message" });
  await secondChatItem.hover();

  // Dismissing the confirm dialog leaves the chat in place.
  page.once("dialog", (dialog) => dialog.dismiss());
  await secondChatItem.locator(".delete-btn").click();
  await expect(page.locator(".chat-item")).toHaveCount(2);

  // Accepting it removes the chat.
  await secondChatItem.hover();
  page.once("dialog", (dialog) => dialog.accept());
  await secondChatItem.locator(".delete-btn").click();
  await expect(page.locator(".chat-item")).toHaveCount(1);
  await expect(page.locator(".chat-item")).toContainText("first chat message");
});
