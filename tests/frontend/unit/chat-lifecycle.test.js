import { afterEach, describe, expect, it, vi } from "vitest";
import { closeApp, jsonResponse, loadApp } from "./helpers/loadApp.js";

const CHATS = [
  { id: "c1", title: "First chat", model: "test-model/default", updated_at: "2024-06-15T11:00:00Z", pinned: false },
  { id: "c2", title: "Second chat", model: "test-model/default", updated_at: "2024-06-15T10:00:00Z", pinned: false },
];

const CHAT_DETAIL = {
  id: "c1",
  model: "test-model/default",
  messages: [
    { role: "user", content: "hello", created_at: "2024-06-15T11:00:00Z" },
    { role: "assistant", content: "hi there", created_at: "2024-06-15T11:00:01Z" },
  ],
};

function fetchFor({ chats = CHATS, chatDetail = CHAT_DETAIL } = {}) {
  return vi.fn((url, opts) => {
    if (opts?.method === "DELETE") return Promise.resolve(jsonResponse({}));
    if (url === "/api/chats") return Promise.resolve(jsonResponse(chats));
    if (url === `/api/chats/${chatDetail.id}`) return Promise.resolve(jsonResponse(chatDetail));
    return Promise.resolve(jsonResponse([]));
  });
}

describe("openChat", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("loads and renders the chat's message history", async () => {
    app = loadApp({ fetchImpl: fetchFor() });
    await app.window.openChat("c1");

    const rows = app.window.document.querySelectorAll(".message-row");
    expect(rows).toHaveLength(2);
    expect(rows[0].classList.contains("user")).toBe(true);
    expect(rows[1].classList.contains("assistant")).toBe(true);
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(false);
  });

  it("selects the chat's model in the dropdown when available", async () => {
    const fetchImpl = fetchFor({
      chatDetail: { ...CHAT_DETAIL, model: "meta/llama-free" },
    });
    app = loadApp({ fetchImpl });
    // Make the model available in the <select> first.
    const select = app.window.document.getElementById("model-select");
    const opt = app.window.document.createElement("option");
    opt.value = "meta/llama-free";
    select.appendChild(opt);

    await app.window.openChat("c1");
    expect(select.value).toBe("meta/llama-free");
  });

  it("shows the empty state for a chat with no messages", async () => {
    const fetchImpl = fetchFor({ chatDetail: { ...CHAT_DETAIL, messages: [] } });
    app = loadApp({ fetchImpl });
    await app.window.openChat("c1");

    expect(app.window.document.querySelector(".empty-state")).not.toBeNull();
  });

  it("is a no-op when re-opening the chat that's already current", async () => {
    const fetchImpl = fetchFor();
    app = loadApp({ fetchImpl });
    await app.window.openChat("c1");
    fetchImpl.mockClear();

    await app.window.openChat("c1");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("does nothing when the chat fails to load", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(jsonResponse({}, { ok: false, status: 404 })));
    app = loadApp({ fetchImpl });
    await app.window.openChat("missing");

    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(true);
  });
});

describe("deleteChat", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("removes the chat from the sidebar", async () => {
    app = loadApp({ fetchImpl: fetchFor() });
    await app.window.loadChats();

    await app.window.deleteChat("c2");
    expect(app.window.document.querySelectorAll(".chat-item")).toHaveLength(1);
    expect(app.window.document.querySelector(".chat-item .title").textContent).toBe("First chat");
  });

  it("resets to the empty state when deleting the currently open chat", async () => {
    app = loadApp({ fetchImpl: fetchFor() });
    await app.window.loadChats();
    await app.window.openChat("c1");

    await app.window.deleteChat("c1");
    expect(app.window.document.querySelector(".empty-state")).not.toBeNull();
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(true);
  });
});

describe("startNewChat", () => {
  let app;

  afterEach(() => {
    if (app) closeApp(app);
  });

  it("clears the current chat and resets the model to the default", async () => {
    app = loadApp({ fetchImpl: fetchFor() });
    await app.window.loadChats();
    await app.window.openChat("c1");

    app.window.startNewChat();
    expect(app.window.document.querySelector(".empty-state")).not.toBeNull();
    expect(app.window.document.getElementById("export-pdf-btn").disabled).toBe(true);
    expect(app.window.document.getElementById("model-select").value).toBe("test-model/default");
  });
});
