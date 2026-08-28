const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("prompt-input");
const sendBtn = document.getElementById("send-btn");
const modelSelect = document.getElementById("model-select");
const newChatBtn = document.getElementById("new-chat-btn");
const chatListEl = document.getElementById("chat-list");

const EMPTY_STATE_HTML = `
  <div class="empty-state">
    <h1>What can I help with?</h1>
    <p>Pick a model on the left and start typing below.</p>
  </div>
`;

let currentChatId = null;
let chats = []; // {id, title, model, updated_at}

const markdownReady = typeof marked !== "undefined" && typeof DOMPurify !== "undefined";
if (markdownReady) {
  marked.setOptions({ breaks: true, gfm: true });
  // Open links from model output in a new tab instead of navigating the app away.
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
} else {
  console.warn("marked/DOMPurify failed to load from CDN; assistant replies will render as plain text.");
}

function setMessageContent(el, role, content) {
  if (role === "assistant" && markdownReady) {
    el.classList.add("markdown-body");
    el.innerHTML = DOMPurify.sanitize(marked.parse(content));
  } else {
    el.classList.remove("markdown-body");
    el.textContent = content;
  }
}

function clearEmptyState() {
  const empty = messagesEl.querySelector(".empty-state");
  if (empty) empty.remove();
}

function formatTime(dateInput) {
  const d = dateInput ? new Date(dateInput) : new Date();
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatRelativeTime(dateInput) {
  const date = new Date(dateInput);
  const diffSec = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay === 1) return "yesterday";
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function renderMessage(role, content, timestamp) {
  clearEmptyState();
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const label = document.createElement("div");
  label.className = "role-label";
  label.textContent = role === "user" ? "You" : "AI";

  const bodyWrap = document.createElement("div");
  bodyWrap.className = "message-body";

  const body = document.createElement("div");
  body.className = "message-content";
  setMessageContent(body, role, content);

  const time = document.createElement("div");
  time.className = "message-time";
  time.textContent = formatTime(timestamp);

  bodyWrap.appendChild(body);
  bodyWrap.appendChild(time);
  row.appendChild(label);
  row.appendChild(bodyWrap);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return { row, contentEl: body, timeEl: time };
}

function renderError(message) {
  clearEmptyState();
  const banner = document.createElement("div");
  banner.className = "error-banner";
  banner.textContent = message;
  messagesEl.appendChild(banner);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function loadModels() {
  try {
    const res = await fetch("/api/models");
    if (!res.ok) return; // keep the default option already in the select
    const models = await res.json();
    if (!Array.isArray(models) || models.length === 0) return;

    const current = modelSelect.value;
    modelSelect.innerHTML = "";
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.name;
      modelSelect.appendChild(opt);
    }
    if ([...modelSelect.options].some((o) => o.value === current)) {
      modelSelect.value = current;
    }
  } catch (err) {
    console.warn("Could not load model list, using default.", err);
  }
}

function renderChatList() {
  chatListEl.innerHTML = "";
  for (const c of chats) {
    const item = document.createElement("div");
    item.className = "chat-item" + (c.id === currentChatId ? " active" : "");

    const main = document.createElement("div");
    main.className = "chat-item-main";

    const title = document.createElement("div");
    title.className = "title";
    title.textContent = c.title;
    title.title = c.title;

    const time = document.createElement("div");
    time.className = "chat-item-time";
    time.textContent = formatRelativeTime(c.updated_at);

    main.appendChild(title);
    main.appendChild(time);

    const delBtn = document.createElement("button");
    delBtn.className = "delete-btn";
    delBtn.textContent = "✕";
    delBtn.setAttribute("aria-label", "Delete chat");
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteChat(c.id);
    });

    item.appendChild(main);
    item.appendChild(delBtn);
    item.addEventListener("click", () => openChat(c.id));
    chatListEl.appendChild(item);
  }
}

async function loadChats() {
  try {
    const res = await fetch("/api/chats");
    if (!res.ok) return;
    chats = await res.json();
    renderChatList();
  } catch (err) {
    console.warn("Could not load chat list.", err);
  }
}

async function openChat(chatId) {
  if (chatId === currentChatId) return;
  try {
    const res = await fetch(`/api/chats/${chatId}`);
    if (!res.ok) return;
    const chat = await res.json();

    currentChatId = chat.id;
    messagesEl.innerHTML = "";
    for (const m of chat.messages) {
      renderMessage(m.role, m.content, m.created_at);
    }
    if (chat.messages.length === 0) messagesEl.innerHTML = EMPTY_STATE_HTML;
    if ([...modelSelect.options].some((o) => o.value === chat.model)) {
      modelSelect.value = chat.model;
    }
    renderChatList();
  } catch (err) {
    console.warn("Could not open chat.", err);
  }
}

async function deleteChat(chatId) {
  try {
    await fetch(`/api/chats/${chatId}`, { method: "DELETE" });
    chats = chats.filter((c) => c.id !== chatId);
    if (chatId === currentChatId) {
      currentChatId = null;
      messagesEl.innerHTML = EMPTY_STATE_HTML;
    }
    renderChatList();
  } catch (err) {
    console.warn("Could not delete chat.", err);
  }
}

function startNewChat() {
  currentChatId = null;
  messagesEl.innerHTML = EMPTY_STATE_HTML;
  renderChatList();
}

async function sendMessage(text) {
  const now = new Date().toISOString();
  renderMessage("user", text, now);

  const assistantMsg = renderMessage("assistant", "", now);
  const assistantEl = assistantMsg.contentEl;
  assistantEl.classList.add("streaming");

  sendBtn.disabled = true;
  let assistantText = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: modelSelect.value, message: text, chat_id: currentChatId }),
    });

    if (!res.ok || !res.body) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || `Request failed with status ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop(); // last chunk may be incomplete

      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith("data:")) continue;
        const dataStr = line.slice(5).trim();
        if (dataStr === "[DONE]") continue;

        let parsed;
        try {
          parsed = JSON.parse(dataStr);
        } catch {
          continue;
        }

        if (parsed.chat_id) {
          const wasNew = currentChatId === null;
          currentChatId = parsed.chat_id;
          if (parsed.is_new_chat) {
            chats.unshift({ id: parsed.chat_id, title: text.slice(0, 50), model: modelSelect.value, updated_at: new Date().toISOString() });
          }
          if (wasNew) renderChatList();
          continue;
        }

        if (parsed.error) {
          throw new Error(typeof parsed.error === "string" ? parsed.error : JSON.stringify(parsed.error));
        }

        const delta = parsed.choices?.[0]?.delta?.content;
        if (delta) {
          assistantText += delta;
          setMessageContent(assistantEl, "assistant", assistantText);
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      }
    }
  } catch (err) {
    assistantMsg.row.remove();
    renderError(`Error: ${err.message}`);
  } finally {
    assistantEl.classList.remove("streaming");
    sendBtn.disabled = false;
    // Refresh from the server so ordering/titles stay in sync across chats.
    loadChats();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  inputEl.style.height = "auto";
  sendMessage(text);
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 200)}px`;
});

newChatBtn.addEventListener("click", startNewChat);

loadModels();
loadChats();

// Keep "5m ago"-style labels fresh without re-fetching from the server.
setInterval(renderChatList, 60_000);
