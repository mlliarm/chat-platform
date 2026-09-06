import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { installFakeChatBackend } from "./helpers/mockApi.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SAMPLE_TXT = path.join(__dirname, "fixtures", "sample.txt");

test("uploading a text file hits the real /api/extract endpoint and folds it into the sent message", async ({ page }) => {
  await installFakeChatBackend(page, { replyChunks: ["Got your file."] });
  await page.goto("/");

  // /api/extract is intentionally NOT mocked here — it's pure local app
  // logic (no OpenRouter dependency), so this exercises the real Flask route.
  await page.locator("#file-input").setInputFiles(SAMPLE_TXT);

  const preview = page.locator("#attachment-preview");
  await expect(preview).toContainText("sample.txt");
  await expect(preview).not.toHaveClass(/error/);

  await page.locator("#prompt-input").fill("see attached");
  await page.locator("#send-btn").click();

  const chip = page.locator(".message-row.user details.attachment-chip");
  await expect(chip.locator("summary")).toHaveText("📎 sample.txt");
  await expect(chip.locator("pre")).toContainText("This is a sample text attachment");
});
