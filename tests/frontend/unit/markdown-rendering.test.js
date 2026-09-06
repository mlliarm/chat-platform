import { afterEach, describe, expect, it } from "vitest";
import { closeApp, loadApp } from "./helpers/loadApp.js";

describe("setMessageContent", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("renders assistant content as sanitized markdown when markdown libs are available", () => {
    app = loadApp();
    const el = app.window.document.createElement("div");
    app.window.setMessageContent(el, "assistant", "**hi**");
    expect(el.classList.contains("markdown-body")).toBe(true);
    expect(el.innerHTML).toBe("<p>**hi**</p>");
  });

  it("does not markdown-render user content even when markdown libs are available", () => {
    app = loadApp();
    const el = app.window.document.createElement("div");
    app.window.setMessageContent(el, "user", "**hi**");
    expect(el.classList.contains("markdown-body")).toBe(false);
    expect(el.textContent).toBe("**hi**");
  });

  it("falls back to plain text for assistant content when markdown libs failed to load", () => {
    app = loadApp({ markdown: false });
    const el = app.window.document.createElement("div");
    app.window.setMessageContent(el, "assistant", "**hi**");
    expect(el.classList.contains("markdown-body")).toBe(false);
    expect(el.textContent).toBe("**hi**");
  });

  it("routes image-content messages to the image renderer regardless of role", () => {
    app = loadApp();
    const el = app.window.document.createElement("div");
    const content = JSON.stringify({ text: "look", image: "data:image/png;base64,abc" });
    app.window.setMessageContent(el, "user", content);
    expect(el.querySelector("img.attached-image")).not.toBeNull();
  });

  it("registers a DOMPurify hook that opens links in a new tab", () => {
    app = loadApp();
    const call = app.window.DOMPurify.addHook.mock.calls.find(([name]) => name === "afterSanitizeAttributes");
    expect(call).toBeDefined();

    const [, hook] = call;
    const node = { tagName: "A", setAttribute: () => {} };
    const spy = [];
    node.setAttribute = (k, v) => spy.push([k, v]);
    hook(node);
    expect(spy).toEqual([
      ["target", "_blank"],
      ["rel", "noopener noreferrer"],
    ]);
  });

  it("does not touch non-anchor nodes in the sanitize hook", () => {
    app = loadApp();
    const [, hook] = app.window.DOMPurify.addHook.mock.calls.find(([name]) => name === "afterSanitizeAttributes");
    let called = false;
    hook({ tagName: "DIV", setAttribute: () => (called = true) });
    expect(called).toBe(false);
  });

  it("wires a custom code renderer into marked that highlights known languages", () => {
    app = loadApp();
    const [config] = app.window.marked.use.mock.calls[0];
    const result = config.renderer.code({ text: "const x = 1;", lang: "javascript" });
    expect(result).toBe('<pre><code class="hljs language-text">const x = 1;</code></pre>');
  });

  it("falls back to highlightAuto for an unrecognized language", () => {
    app = loadApp();
    app.window.hljs.getLanguage = () => false;
    const [config] = app.window.marked.use.mock.calls[0];
    const result = config.renderer.code({ text: "mystery code", lang: "not-a-real-lang" });
    expect(result).toBe('<pre><code class="hljs">mystery code</code></pre>');
  });
});
