import { expect, test } from "@playwright/test";
import { mockModels } from "./helpers/mockApi.js";

const MODELS = [
  { id: "openai/gpt-4o-mini", name: "GPT-4o mini", is_free: false },
  { id: "meta/llama-free", name: "Llama Free", is_free: true },
];

test("free-only toggle filters the model dropdown", async ({ page }) => {
  await mockModels(page, MODELS);
  await page.goto("/");

  const select = page.locator("#model-select");
  await expect(select.locator("option")).toHaveCount(2);

  // The checkbox itself is visually hidden behind its `.switch` label
  // wrapper (that's what's actually clickable/visible to a real user).
  await page.locator("label.switch").click();
  await expect(select.locator("option")).toHaveCount(1);
  await expect(select.locator("option")).toHaveText("Llama Free (Free)");

  await page.locator("label.switch").click();
  await expect(select.locator("option")).toHaveCount(2);
});

test("free-only preference survives a reload via localStorage", async ({ page }) => {
  await mockModels(page, MODELS);
  await page.goto("/");
  // The checkbox itself is visually hidden behind its `.switch` label
  // wrapper (that's what's actually clickable/visible to a real user).
  await page.locator("label.switch").click();

  await page.reload();
  await expect(page.locator("#free-only-toggle")).toBeChecked();
  await expect(page.locator("#model-select option")).toHaveCount(1);
});
