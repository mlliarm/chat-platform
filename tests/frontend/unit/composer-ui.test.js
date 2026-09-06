import { afterEach, describe, expect, it, vi } from "vitest";
import { closeApp, jsonResponse, loadApp } from "./helpers/loadApp.js";
import { chunkFrames, makeStreamingResponse } from "./helpers/fakeSSE.js";

describe("composer form submission", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("trims the message and clears the textarea on submit", async () => {
    const frames = [{ chat_id: "c1", is_new_chat: true }, ...chunkFrames(["ok"])];
    app = loadApp({
      fetchImpl: vi.fn((url) => {
        if (url === "/api/chat") return Promise.resolve(makeStreamingResponse(frames));
        return Promise.resolve(jsonResponse([]));
      }),
    });
    const { window } = app;
    const input = window.document.getElementById("prompt-input");
    input.value = "  hello there  \n";
    window.document.getElementById("chat-form").requestSubmit();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(input.value).toBe("");
    const userContent = window.document.querySelector(".message-row.user .message-content");
    expect(userContent.textContent).toBe("hello there");
  });

  it("blocks submission when there is no text and no attachment", () => {
    app = loadApp();
    const { window } = app;
    const fetchSpy = window.fetch;
    window.document.getElementById("prompt-input").value = "   ";
    window.document.getElementById("chat-form").requestSubmit();

    expect(fetchSpy).not.toHaveBeenCalledWith("/api/chat", expect.anything());
  });

  it("allows submission with an attachment even when the text is empty", async () => {
    const frames = [{ chat_id: "c1", is_new_chat: true }, ...chunkFrames(["ok"])];
    app = loadApp({
      fetchImpl: vi.fn((url) => {
        if (url === "/api/extract") return Promise.resolve(jsonResponse({ filename: "n.txt", text: "body" }));
        if (url === "/api/chat") return Promise.resolve(makeStreamingResponse(frames));
        return Promise.resolve(jsonResponse([]));
      }),
    });
    const { window } = app;
    const fileInput = window.document.getElementById("file-input");
    const file = new window.File([new Uint8Array(10)], "n.txt", { type: "text/plain" });
    Object.defineProperty(fileInput, "files", { value: [file], configurable: true });
    fileInput.dispatchEvent(new window.Event("change"));
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    window.document.getElementById("prompt-input").value = "";
    window.document.getElementById("chat-form").requestSubmit();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(window.document.querySelectorAll(".message-row")).toHaveLength(2);
  });
});

describe("Enter / Shift+Enter in the composer", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("Enter submits the form", () => {
    app = loadApp();
    const { window } = app;
    const form = window.document.getElementById("chat-form");
    const submitSpy = vi.fn((e) => e.preventDefault());
    form.addEventListener("submit", submitSpy);

    window.document.getElementById("prompt-input").dispatchEvent(
      new window.KeyboardEvent("keydown", { key: "Enter", shiftKey: false, bubbles: true, cancelable: true }),
    );
    expect(submitSpy).toHaveBeenCalled();
  });

  it("Shift+Enter does not submit the form", () => {
    app = loadApp();
    const { window } = app;
    const form = window.document.getElementById("chat-form");
    const submitSpy = vi.fn((e) => e.preventDefault());
    form.addEventListener("submit", submitSpy);

    window.document.getElementById("prompt-input").dispatchEvent(
      new window.KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true, cancelable: true }),
    );
    expect(submitSpy).not.toHaveBeenCalled();
  });
});

describe("textarea auto-resize", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("grows the textarea height to fit its content", () => {
    app = loadApp();
    const { window } = app;
    const input = window.document.getElementById("prompt-input");
    Object.defineProperty(input, "scrollHeight", { value: 120, configurable: true });

    input.dispatchEvent(new window.Event("input"));
    expect(input.style.height).toBe("120px");
  });

  it("clamps the textarea height to 200px", () => {
    app = loadApp();
    const { window } = app;
    const input = window.document.getElementById("prompt-input");
    Object.defineProperty(input, "scrollHeight", { value: 500, configurable: true });

    input.dispatchEvent(new window.Event("input"));
    expect(input.style.height).toBe("200px");
  });
});
