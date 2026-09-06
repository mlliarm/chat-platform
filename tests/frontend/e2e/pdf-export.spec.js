import { expect, test } from "@playwright/test";
import { installFakeChatBackend } from "./helpers/mockApi.js";

// The real /api/chats/<id>/export endpoint sets Content-Disposition:
// attachment, so clicking the button triggers a browser download rather than
// a page navigation. Byte-level PDF correctness is already covered by the
// Python pytest suite (test_markdown_pdf.py) — this just checks the button
// targets the right chat's export URL.
test("clicking export downloads a PDF from the chat's export URL", async ({ page }) => {
  await installFakeChatBackend(page);
  await page.route("**/api/chats/*/export", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/pdf",
      headers: { "Content-Disposition": 'attachment; filename="chat.pdf"' },
      body: Buffer.from("%PDF-1.4 fake pdf content"),
    }),
  );
  await page.goto("/");

  await page.locator("#prompt-input").fill("a chat to export");
  await page.locator("#send-btn").click();
  await expect(page.locator("#export-pdf-btn")).toBeEnabled();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.locator("#export-pdf-btn").click(),
  ]);
  expect(download.url()).toMatch(/\/api\/chats\/chat-1\/export$/);
});

test("the export button stays disabled with no open chat, so it can't be clicked", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#export-pdf-btn")).toBeDisabled();
});
