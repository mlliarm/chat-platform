import { buildSSEText, chunkFrames } from "../../unit/helpers/fakeSSE.js";

export { chunkFrames };

/** Mocks /api/chat with a successful SSE stream built from the given frames. */
export async function mockChatStream(page, frames) {
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: buildSSEText(frames) }),
  );
}

/** Mocks /api/chat with a non-ok JSON error response (the pre-stream error path). */
export async function mockChatError(page, errorBody, { status = 400 } = {}) {
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(errorBody) }),
  );
}

/** Mocks /api/models with a fixed catalog, since the real endpoint proxies OpenRouter. */
export async function mockModels(page, models) {
  await page.route("**/api/models", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(models) }),
  );
}

/**
 * Installs a fully in-memory fake backend for /api/chats* and /api/chat, so
 * chat CRUD flows (list/open/pin/delete + creating a chat by sending a
 * message) can be exercised end to end in a real browser without touching
 * OpenRouter or the real Flask/SQLite backend. Real chat persistence and PDF
 * export are already covered by the Python pytest suite; this is about the
 * frontend's request/response contract and DOM updates.
 */
export async function installFakeChatBackend(page, { defaultModel = "test-model/default", replyChunks = ["Mock reply."] } = {}) {
  const chats = new Map();
  let counter = 0;

  await page.route("**/api/chats**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const method = req.method();
    const parts = url.pathname.split("/").filter(Boolean); // ["api", "chats", id?, "pin"?]

    if (parts.length === 2 && method === "GET") {
      const list = [...chats.values()]
        .sort((a, b) => b.pinned - a.pinned || b.updated_at.localeCompare(a.updated_at))
        .map(({ id, title, model, updated_at, pinned }) => ({ id, title, model, updated_at, pinned }));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(list) });
    }

    if (parts.length === 3 && parts[2] !== "pin") {
      const chat = chats.get(parts[2]);
      if (method === "GET") {
        if (!chat) return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ id: chat.id, model: chat.model, messages: chat.messages }),
        });
      }
      if (method === "DELETE") {
        chats.delete(parts[2]);
        return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      }
    }

    if (parts.length === 4 && parts[3] === "pin" && method === "POST") {
      const chat = chats.get(parts[2]);
      const { pinned } = req.postDataJSON();
      if (chat) chat.pinned = pinned;
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    }

    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  await page.route("**/api/chat", async (route) => {
    const req = route.request();
    const body = req.postDataJSON();
    const isNew = !body.chat_id;
    const chatId = body.chat_id || `chat-${++counter}`;
    const now = new Date().toISOString();

    if (isNew) {
      chats.set(chatId, {
        id: chatId,
        title: (body.message || "").slice(0, 50) || "New chat",
        model: body.model || defaultModel,
        updated_at: now,
        pinned: false,
        messages: [],
      });
    }
    const chat = chats.get(chatId);
    const userContent = body.image ? JSON.stringify({ text: body.message, image: body.image }) : body.message;
    chat.messages.push({ role: "user", content: userContent, created_at: now });
    chat.messages.push({ role: "assistant", content: replyChunks.join(""), created_at: now });
    chat.updated_at = now;

    const frames = [{ chat_id: chatId, is_new_chat: isNew }, ...chunkFrames(replyChunks)];
    return route.fulfill({ status: 200, contentType: "text/event-stream", body: buildSSEText(frames) });
  });

  return chats;
}
