import { afterEach, describe, expect, it, vi } from "vitest";
import { closeApp, jsonResponse, loadApp } from "./helpers/loadApp.js";
import { chunkFrames, makeErrorResponse, makeStreamingResponse } from "./helpers/fakeSSE.js";

function fetchStreaming(frames, { chunkSize } = {}) {
  return vi.fn((url) => {
    if (url === "/api/chat") return Promise.resolve(makeStreamingResponse(frames, { chunkSize }));
    return Promise.resolve(jsonResponse([]));
  });
}

describe("sendMessage", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("renders the user message immediately and streams the assistant reply", async () => {
    const frames = [{ chat_id: "c1", is_new_chat: true }, ...chunkFrames(["Hel", "lo!"])];
    app = loadApp({ fetchImpl: fetchStreaming(frames) });

    await app.window.sendMessage("hi there");

    const rows = app.window.document.querySelectorAll(".message-row");
    expect(rows).toHaveLength(2);
    expect(rows[0].classList.contains("user")).toBe(true);
    expect(rows[0].querySelector(".message-content").textContent).toBe("hi there");
    expect(rows[1].classList.contains("assistant")).toBe(true);
    expect(rows[1].querySelector(".message-content").innerHTML).toBe("<p>Hello!</p>");
  });

  it("adds a new chat to the sidebar when the backend reports is_new_chat", async () => {
    const frames = [{ chat_id: "new-chat-id", is_new_chat: true }, ...chunkFrames(["ok"])];
    app = loadApp({ fetchImpl: fetchStreaming(frames) });

    await app.window.sendMessage("first message in a new chat");

    const items = app.window.document.querySelectorAll(".chat-item");
    expect(items).toHaveLength(1);
    expect(items[0].querySelector(".title").textContent).toBe("first message in a new chat");
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(false);
  });

  it("does not duplicate the sidebar entry for an existing chat", async () => {
    const frames = [{ chat_id: "existing-chat" }, ...chunkFrames(["ok"])];
    app = loadApp({ fetchImpl: fetchStreaming(frames) });

    await app.window.sendMessage("a reply in an existing chat");
    expect(app.window.document.querySelectorAll(".chat-item")).toHaveLength(0);
  });

  it("re-enables the send button and refreshes the chat list when streaming finishes", async () => {
    const loadChatsSpy = vi.fn(() => Promise.resolve(jsonResponse([])));
    const frames = chunkFrames(["done"]);
    app = loadApp({ fetchImpl: fetchStreaming(frames) });
    app.window.fetch = vi.fn((url) => {
      if (url === "/api/chat") return Promise.resolve(makeStreamingResponse(frames));
      if (url === "/api/chats") return loadChatsSpy();
      return Promise.resolve(jsonResponse([]));
    });

    await app.window.sendMessage("hi");

    expect(app.window.document.getElementById("send-btn").disabled).toBe(false);
    expect(loadChatsSpy).toHaveBeenCalled();
  });

  it("shows a friendly error and removes the empty assistant bubble when the request is rejected", async () => {
    const errorBody = { error: "No endpoints found that support image input" };
    app = loadApp({
      fetchImpl: vi.fn((url) => {
        if (url === "/api/chat") return Promise.resolve(makeErrorResponse(errorBody));
        return Promise.resolve(jsonResponse([]));
      }),
    });

    await app.window.sendMessage("describe this photo");

    const rows = app.window.document.querySelectorAll(".message-row");
    expect(rows).toHaveLength(1); // only the user's message remains
    const banner = app.window.document.querySelector(".error-banner");
    expect(banner).not.toBeNull();
    expect(banner.textContent).toMatch(/vision-capable model/);
  });

  it("reverts the optimistic image flag when the backend rolls back a rejected image message", async () => {
    // Start from a chat with no image in its history (chatHasImage = false).
    let call = 0;
    app = loadApp({
      fetchImpl: vi.fn((url) => {
        if (url === "/api/chats/c1") {
          return Promise.resolve(jsonResponse({ id: "c1", model: "test-model/default", messages: [] }));
        }
        if (url === "/api/chat") {
          call += 1;
          // Turn 1: an image attachment gets rejected and rolled back.
          if (call === 1) {
            return Promise.resolve(makeStreamingResponse([{ error: "unrelated failure", rolled_back: true }]));
          }
          // Turn 2: no attachment, but the model still can't handle images —
          // if chatHasImage were incorrectly left `true` by turn 1, this would
          // render the "earlier in it" message instead of the generic one.
          return Promise.resolve(makeStreamingResponse([{ error: "unsupported image modality" }]));
        }
        return Promise.resolve(jsonResponse([]));
      }),
    });
    await app.window.openChat("c1");

    const fileInput = app.window.document.getElementById("file-input");
    const file = new app.window.File([new Uint8Array(10)], "cat.png", { type: "image/png" });
    Object.defineProperty(fileInput, "files", { value: [file], configurable: true });
    fileInput.dispatchEvent(new app.window.Event("change"));
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    await app.window.sendMessage("what is this?");

    await app.window.sendMessage("second message, no attachment");

    const banners = app.window.document.querySelectorAll(".error-banner");
    expect(banners).toHaveLength(2);
    expect(banners[1].textContent).not.toMatch(/earlier in it/);
    expect(banners[1].textContent).toMatch(/doesn't support image input/);
  });

  it("clears the chat entirely when the backend reports chat_deleted", async () => {
    const frames = [{ error: "boom", chat_deleted: true }];
    app = loadApp({ fetchImpl: fetchStreaming(frames) });

    await app.window.sendMessage("this whole chat gets rolled back");

    // The empty state is set and then immediately cleared by renderError's
    // own clearEmptyState() call, leaving just the error banner behind.
    expect(app.window.document.querySelectorAll(".message-row")).toHaveLength(0);
    expect(app.window.document.querySelector(".error-banner")).not.toBeNull();
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(true);
  });

  it("sends an image attachment as a JSON image envelope and marks the chat as having an image", async () => {
    const frames = [{ chat_id: "c1", is_new_chat: true }, ...chunkFrames(["I see a cat"])];
    let sentBody;
    app = loadApp({
      fetchImpl: vi.fn((url, opts) => {
        if (url === "/api/chat") {
          sentBody = JSON.parse(opts.body);
          return Promise.resolve(makeStreamingResponse(frames));
        }
        return Promise.resolve(jsonResponse([]));
      }),
    });

    const fileInput = app.window.document.getElementById("file-input");
    const file = new app.window.File([new Uint8Array(10)], "cat.png", { type: "image/png" });
    Object.defineProperty(fileInput, "files", { value: [file], configurable: true });
    fileInput.dispatchEvent(new app.window.Event("change"));
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    await app.window.sendMessage("what is this?");

    expect(sentBody.image).toMatch(/^data:image\/png;base64,/);
    const userRow = app.window.document.querySelector(".message-row.user");
    expect(userRow.querySelector("img.attached-image")).not.toBeNull();
  });

  it("folds a text attachment into the outgoing message with the attachment marker", async () => {
    const frames = [{ chat_id: "c1", is_new_chat: true }, ...chunkFrames(["ok"])];
    let sentBody;
    app = loadApp({
      fetchImpl: vi.fn((url, opts) => {
        if (url === "/api/extract") return Promise.resolve(jsonResponse({ filename: "notes.txt", text: "the file body" }));
        if (url === "/api/chat") {
          sentBody = JSON.parse(opts.body);
          return Promise.resolve(makeStreamingResponse(frames));
        }
        return Promise.resolve(jsonResponse([]));
      }),
    });

    const fileInput = app.window.document.getElementById("file-input");
    const file = new app.window.File([new Uint8Array(10)], "notes.txt", { type: "text/plain" });
    Object.defineProperty(fileInput, "files", { value: [file], configurable: true });
    fileInput.dispatchEvent(new app.window.Event("change"));
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    await app.window.sendMessage("see attached");

    expect(sentBody.message).toBe("see attached\n\n<!--attachment:notes.txt-->\nthe file body\n<!--/attachment-->");
    const chip = app.window.document.querySelector(".message-row.user details.attachment-chip");
    expect(chip.querySelector("summary").textContent).toBe("📎 notes.txt");
  });

  it("handles SSE frames split across multiple stream chunks", async () => {
    const frames = [{ chat_id: "c1", is_new_chat: true }, ...chunkFrames(["Hello", " world"])];
    app = loadApp({ fetchImpl: fetchStreaming(frames, { chunkSize: 7 }) });

    await app.window.sendMessage("hi");

    const assistantRow = app.window.document.querySelector(".message-row.assistant");
    expect(assistantRow.querySelector(".message-content").innerHTML).toBe("<p>Hello world</p>");
  });
});
