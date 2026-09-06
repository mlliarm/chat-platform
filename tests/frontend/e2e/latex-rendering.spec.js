import { expect, test } from "@playwright/test";
import { installFakeChatBackend } from "./helpers/mockApi.js";

async function sendAndGetReply(page, prompt) {
  await page.locator("#prompt-input").fill(prompt);
  await page.locator("#send-btn").click();
  return page.locator(".message-row.assistant .message-content");
}

test("typesets inline math in a streamed reply", async ({ page }) => {
  await installFakeChatBackend(page, { replyChunks: ["The identity ", "$e^{i\\pi} + 1 = 0$", " is famous."] });
  await page.goto("/");

  const reply = await sendAndGetReply(page, "euler");

  await expect(reply.locator(".math-inline mjx-container")).toHaveCount(1);
  await expect(reply).toContainText("The identity");
  await expect(reply).toContainText("is famous.");
});

test("typesets display math, including a multi-line environment", async ({ page }) => {
  const latex = "$$\n\\begin{aligned}\na &= b + c \\\\\nd &= e - f\n\\end{aligned}\n$$";
  await installFakeChatBackend(page, { replyChunks: ["Here:\n\n", latex] });
  await page.goto("/");

  const reply = await sendAndGetReply(page, "aligned");

  const display = reply.locator(".math-display mjx-container");
  await expect(display).toHaveCount(1);
  // A rendered \begin{aligned} keeps both rows; a markdown-mangled one collapses
  // the `\\` row break and MathJax emits a single-row error instead.
  await expect(display).toContainText("a=b+c");
  await expect(display).toContainText("d=e−f");
});

test("leaves math inside a code block as literal source", async ({ page }) => {
  await installFakeChatBackend(page, { replyChunks: ["```\n$x^2$\n```"] });
  await page.goto("/");

  const reply = await sendAndGetReply(page, "code");

  await expect(reply.locator("pre code")).toContainText("$x^2$");
  await expect(reply.locator("mjx-container")).toHaveCount(0);
});

test("does not typeset currency amounts in prose", async ({ page }) => {
  await installFakeChatBackend(page, { replyChunks: ["It costs $5 and then $10 more."] });
  await page.goto("/");

  const reply = await sendAndGetReply(page, "price");

  await expect(reply).toContainText("It costs $5 and then $10 more.");
  await expect(reply.locator("mjx-container")).toHaveCount(0);
});
