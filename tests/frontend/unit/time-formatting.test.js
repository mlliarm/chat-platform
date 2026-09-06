import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { closeApp, loadApp, setNow } from "./helpers/loadApp.js";

describe("formatTime / formatRelativeTime", () => {
  let app;

  beforeEach(() => {
    app = loadApp();
  });

  afterEach(() => {
    closeApp(app);
  });

  it("formatTime renders a locale time string", () => {
    const result = app.window.formatTime("2024-01-01T12:34:00Z");
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(0);
  });

  it.each([
    [30, "just now"],
    [90, "1m ago"],
    [59 * 60, "59m ago"],
    [2 * 3600, "2h ago"],
    [23 * 3600, "23h ago"],
  ])("formatRelativeTime: %d seconds ago -> %s", (secondsAgo, expected) => {
    const now = new Date("2024-06-15T12:00:00Z");
    setNow(app, now);
    const then = new Date(now.getTime() - secondsAgo * 1000);
    expect(app.window.formatRelativeTime(then.toISOString())).toBe(expected);
  });

  it("formatRelativeTime says 'yesterday' for exactly one day ago", () => {
    const now = new Date("2024-06-15T12:00:00Z");
    setNow(app, now);
    const then = new Date(now.getTime() - 25 * 3600 * 1000);
    expect(app.window.formatRelativeTime(then.toISOString())).toBe("yesterday");
  });

  it("formatRelativeTime uses 'Nd ago' between 2 and 6 days", () => {
    const now = new Date("2024-06-15T12:00:00Z");
    setNow(app, now);
    const then = new Date(now.getTime() - 3 * 24 * 3600 * 1000);
    expect(app.window.formatRelativeTime(then.toISOString())).toBe("3d ago");
  });

  it("formatRelativeTime falls back to a locale date at 7+ days", () => {
    const now = new Date("2024-06-15T12:00:00Z");
    setNow(app, now);
    const then = new Date(now.getTime() - 10 * 24 * 3600 * 1000);
    const result = app.window.formatRelativeTime(then.toISOString());
    expect(result).not.toMatch(/ago|yesterday/);
  });
});
