import { expect, test } from "@playwright/test";

// static/style.css only defines a `prefers-color-scheme: dark` override (no
// width-based responsive breakpoint exists in the stylesheet), so this
// covers that: the page's background actually changes between color schemes.
test("the page background changes between light and dark color schemes", async ({ page }) => {
  await page.goto("/");

  await page.emulateMedia({ colorScheme: "light" });
  const lightBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

  await page.emulateMedia({ colorScheme: "dark" });
  const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

  expect(darkBg).not.toBe(lightBg);
});
