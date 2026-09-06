import { afterEach, describe, expect, it } from "vitest";
import { closeApp, loadApp } from "./helpers/loadApp.js";

// jsdom deliberately doesn't implement real navigation (and its Location's
// `href` is a non-configurable, unforgeable property), so the button's
// actual `window.location.href = ...` navigation is verified in the
// Playwright e2e suite (pdf-export.spec.js) instead. This file covers the
// button's enabled/disabled state tracking, which is pure DOM/state logic.
describe("export-pdf button state", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("is disabled when there is no open chat", () => {
    app = loadApp();
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(true);
  });

  it("is enabled once a chat is set as current", () => {
    app = loadApp();
    app.window.setCurrentChatId("c1");
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(false);
  });

  it("is disabled again after the current chat is cleared", () => {
    app = loadApp();
    app.window.setCurrentChatId("c1");
    app.window.setCurrentChatId(null);
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(true);
  });
});
