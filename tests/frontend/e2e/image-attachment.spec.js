import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { installFakeChatBackend } from "./helpers/mockApi.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SAMPLE_PNG = path.join(__dirname, "fixtures", "sample.png");

test("attaching an image shows a preview and sends it as an image message", async ({ page }) => {
  await installFakeChatBackend(page, { replyChunks: ["I see a red square."] });
  await page.goto("/");

  await page.locator("#file-input").setInputFiles(SAMPLE_PNG);

  const preview = page.locator("#attachment-preview");
  await expect(preview).toBeVisible();
  await expect(preview.locator("img")).toBeVisible();
  await expect(preview).toContainText("sample.png");

  await page.locator("#prompt-input").fill("what is this?");
  await page.locator("#send-btn").click();

  await expect(page.locator(".message-row.user img.attached-image")).toBeVisible();
  await expect(page.locator(".message-row.assistant .message-content")).toContainText("I see a red square.");
  await expect(preview).toBeHidden();
});
