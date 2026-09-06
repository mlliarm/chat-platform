import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { closeApp, loadApp } from "./helpers/loadApp.js";

describe("extractErrorMessage", () => {
  let app;

  beforeEach(() => {
    app = loadApp();
  });

  afterEach(() => {
    closeApp(app);
  });

  it("pulls the human message out of a JSON error envelope", () => {
    const raw = JSON.stringify({ error: { message: "No endpoints found that support image input", code: 404 } });
    expect(app.window.extractErrorMessage(raw)).toBe("No endpoints found that support image input");
  });

  it("handles a plain string error field", () => {
    const raw = JSON.stringify({ error: "boom" });
    expect(app.window.extractErrorMessage(raw)).toBe("boom");
  });

  it("returns the raw text when it isn't JSON", () => {
    expect(app.window.extractErrorMessage("plain failure")).toBe("plain failure");
  });

  it("returns the raw text when JSON has no error field", () => {
    const raw = JSON.stringify({ foo: "bar" });
    expect(app.window.extractErrorMessage(raw)).toBe(raw);
  });
});

describe("friendlyAttachmentError", () => {
  let app;

  beforeEach(() => {
    app = loadApp();
  });

  afterEach(() => {
    closeApp(app);
  });

  it("rewrites a missing-vision error when the current message has an image attachment", () => {
    const msg = app.window.friendlyAttachmentError(
      "No endpoints found that support image input",
      { kind: "image" },
      false,
    );
    expect(msg).toMatch(/can't see images/);
  });

  it("rewrites a missing-vision error when an earlier turn in the chat had an image", () => {
    const msg = app.window.friendlyAttachmentError("unsupported image modality", { kind: "text" }, true);
    expect(msg).toMatch(/earlier in it/);
  });

  it("rewrites a missing-vision error with a generic message when neither applies", () => {
    const msg = app.window.friendlyAttachmentError("unsupported modality: image", null, false);
    expect(msg).toMatch(/doesn't support image input/);
  });

  it("rewrites a context-overflow error for a pdf attachment", () => {
    const msg = app.window.friendlyAttachmentError(
      "maximum context length exceeded",
      { kind: "text", fileType: "pdf" },
      false,
    );
    expect(msg).toMatch(/PDF is too long/);
  });

  it("rewrites a context-overflow error for a non-pdf text attachment", () => {
    const msg = app.window.friendlyAttachmentError(
      "too many tokens",
      { kind: "text", fileType: "text" },
      false,
    );
    expect(msg).toMatch(/file is too long/);
  });

  it("passes unrelated messages through unchanged", () => {
    const msg = app.window.friendlyAttachmentError("rate limit exceeded", null, false);
    expect(msg).toBe("rate limit exceeded");
  });

  it("does not treat a context-overflow message as such without a text attachment", () => {
    const msg = app.window.friendlyAttachmentError("token limit exceeded", null, false);
    expect(msg).toBe("token limit exceeded");
  });
});
