import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { closeApp, loadApp } from "./helpers/loadApp.js";

describe("renderPlainOrAttachmentContent", () => {
  let app;

  beforeEach(() => {
    app = loadApp();
  });

  afterEach(() => {
    closeApp(app);
  });

  it("renders plain content as-is when there is no attachment marker", () => {
    const el = app.window.document.createElement("div");
    app.window.renderPlainOrAttachmentContent(el, "just a normal message");
    expect(el.textContent).toBe("just a normal message");
    expect(el.querySelector("details")).toBeNull();
  });

  it("splits typed text from the attachment chip when a marker is present", () => {
    const content = "check this out\n\n<!--attachment:notes.txt-->\nfile body here\n<!--/attachment-->";
    const el = app.window.document.createElement("div");
    app.window.renderPlainOrAttachmentContent(el, content);

    const details = el.querySelector("details.attachment-chip");
    expect(details).not.toBeNull();
    expect(details.querySelector("summary").textContent).toBe("📎 notes.txt");
    expect(details.querySelector("pre").textContent).toBe("file body here");
    expect(el.textContent).toContain("check this out");
  });

  it("renders only the attachment chip when there is no typed text", () => {
    const content = "\n\n<!--attachment:notes.txt-->\nfile body here\n<!--/attachment-->";
    const el = app.window.document.createElement("div");
    app.window.renderPlainOrAttachmentContent(el, content);

    expect(el.querySelectorAll("div").length).toBe(0);
    expect(el.querySelector("details.attachment-chip")).not.toBeNull();
  });

  it("treats an unterminated attachment marker as plain text", () => {
    const content = "check this out\n\n<!--attachment:notes.txt-->\nfile body here";
    const el = app.window.document.createElement("div");
    app.window.renderPlainOrAttachmentContent(el, content);
    expect(el.textContent).toBe(content);
    expect(el.querySelector("details")).toBeNull();
  });
});
