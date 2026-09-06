import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { closeApp, loadApp } from "./helpers/loadApp.js";

describe("tryParseImageContent", () => {
  let app;

  beforeEach(() => {
    app = loadApp();
  });

  afterEach(() => {
    closeApp(app);
  });

  it("parses a valid image content envelope", () => {
    const content = JSON.stringify({ text: "hi", image: "data:image/png;base64,abc" });
    const result = app.window.tryParseImageContent(content);
    expect(result).toEqual({ text: "hi", image: "data:image/png;base64,abc" });
  });

  it("returns null for malformed JSON that starts with {", () => {
    expect(app.window.tryParseImageContent("{not json")).toBeNull();
  });

  it("returns null for JSON without an image key", () => {
    expect(app.window.tryParseImageContent(JSON.stringify({ text: "hi" }))).toBeNull();
  });

  it("returns null for a plain string that doesn't start with {", () => {
    expect(app.window.tryParseImageContent("hello world")).toBeNull();
  });

  it("returns null for non-string input", () => {
    expect(app.window.tryParseImageContent(null)).toBeNull();
    expect(app.window.tryParseImageContent(undefined)).toBeNull();
    expect(app.window.tryParseImageContent(42)).toBeNull();
  });
});

describe("renderImageContent", () => {
  let app;

  beforeEach(() => {
    app = loadApp();
  });

  afterEach(() => {
    closeApp(app);
  });

  it("renders both the caption text and the image", () => {
    const el = app.window.document.createElement("div");
    app.window.renderImageContent(el, { text: "a caption", image: "data:image/png;base64,abc" });

    const img = el.querySelector("img.attached-image");
    expect(img).not.toBeNull();
    expect(img.getAttribute("src")).toBe("data:image/png;base64,abc");
    expect(el.textContent).toContain("a caption");
  });

  it("renders only the image when there is no caption text", () => {
    const el = app.window.document.createElement("div");
    app.window.renderImageContent(el, { text: "", image: "data:image/png;base64,abc" });

    expect(el.querySelectorAll("div").length).toBe(0);
    expect(el.querySelector("img.attached-image")).not.toBeNull();
  });
});
