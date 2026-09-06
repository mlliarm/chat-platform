import { afterEach, describe, expect, it, vi } from "vitest";
import { closeApp, jsonResponse, loadApp } from "./helpers/loadApp.js";

const CHATS = [
  { id: "c1", title: "First chat", model: "m1", updated_at: "2024-06-15T11:00:00Z", pinned: false },
  { id: "c2", title: "Second chat", model: "m1", updated_at: "2024-06-15T10:00:00Z", pinned: true },
];

describe("renderChatList", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("renders one item per chat with pin state and title", async () => {
    app = loadApp({ fetchImpl: vi.fn(() => Promise.resolve(jsonResponse(CHATS))) });
    await app.window.loadChats();

    const items = app.window.document.querySelectorAll(".chat-item");
    expect(items).toHaveLength(2);
    expect(items[0].querySelector(".title").textContent).toBe("First chat");
    expect(items[0].querySelector(".pin-btn").classList.contains("pinned")).toBe(false);
    expect(items[1].querySelector(".pin-btn").classList.contains("pinned")).toBe(true);
  });

  it("marks the currently open chat as active", async () => {
    app = loadApp({ fetchImpl: vi.fn(() => Promise.resolve(jsonResponse(CHATS))) });
    await app.window.loadChats();
    app.window.setCurrentChatId("c2");
    app.window.renderChatList();

    const items = app.window.document.querySelectorAll(".chat-item");
    expect(items[0].classList.contains("active")).toBe(false);
    expect(items[1].classList.contains("active")).toBe(true);
  });

  it("deletes a chat only after the user confirms", async () => {
    const confirmImpl = vi.fn(() => false);
    app = loadApp({ fetchImpl: vi.fn(() => Promise.resolve(jsonResponse(CHATS))), confirmImpl });
    await app.window.loadChats();

    app.window.document.querySelectorAll(".delete-btn")[0].dispatchEvent(
      new app.window.Event("click", { bubbles: true }),
    );
    expect(confirmImpl).toHaveBeenCalled();
    expect(app.window.document.querySelectorAll(".chat-item")).toHaveLength(2);
  });

  it("deletes a chat when the user confirms", async () => {
    const fetchImpl = vi.fn((url, opts) => {
      if (opts?.method === "DELETE") return Promise.resolve(jsonResponse({}));
      return Promise.resolve(jsonResponse(CHATS));
    });
    app = loadApp({ fetchImpl, confirmImpl: vi.fn(() => true) });
    await app.window.loadChats();

    app.window.document.querySelectorAll(".delete-btn")[0].dispatchEvent(
      new app.window.Event("click", { bubbles: true }),
    );
    await new Promise((r) => setTimeout(r, 0));

    expect(fetchImpl).toHaveBeenCalledWith("/api/chats/c1", { method: "DELETE" });
  });
});

describe("togglePin", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("posts the new pinned state and reloads the chat list", async () => {
    const fetchImpl = vi.fn((url) => {
      if (url === "/api/chats/c1/pin") return Promise.resolve(jsonResponse({}));
      return Promise.resolve(jsonResponse(CHATS));
    });
    app = loadApp({ fetchImpl });
    await app.window.togglePin("c1", true);

    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/chats/c1/pin",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ pinned: true }),
      }),
    );
    expect(fetchImpl).toHaveBeenCalledWith("/api/chats");
  });
});

describe("loadChats", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("does nothing to the DOM when the request fails", async () => {
    app = loadApp({ fetchImpl: vi.fn(() => Promise.resolve(jsonResponse([], { ok: false, status: 500 }))) });
    await app.window.loadChats();
    expect(app.window.document.querySelectorAll(".chat-item")).toHaveLength(0);
  });
});
