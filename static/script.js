const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("prompt-input");
const sendBtn = document.getElementById("send-btn");
const modelSelect = document.getElementById("model-select");
const newChatBtn = document.getElementById("new-chat-btn");
const chatListEl = document.getElementById("chat-list");
const freeOnlyToggle = document.getElementById("free-only-toggle");
const attachBtn = document.getElementById("attach-btn");
const fileInput = document.getElementById("file-input");
const attachmentPreviewEl = document.getElementById("attachment-preview");

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ATTACHMENT_MARKER_RE = /\n\n<!--attachment:(.+?)-->\n([\s\S]*?)\n<!--\/attachment-->$/;

const EMPTY_STATE_HTML = `
  <div class="empty-state">
    <h1>What can I help with?</h1>
    <p>Pick a model on the left and start typing below.</p>
  </div>
`;

let currentChatId = null;
let chats = []; // {id, title, model, updated_at}
let chatHasImage = false; // whether the currently open chat has an image anywhere in its history

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

function tryParseImageContent(content) {
  if (typeof content !== "string" || !content.startsWith("{")) return null;
  try {
    const parsed = JSON.parse(content);
    if (parsed && typeof parsed === "object" && parsed.image) return parsed;
  } catch {
    // not JSON, fall through
  }
  return null;
}

function renderImageContent(el, { text, image }) {
  el.textContent = "";
  if (text) {
    const p = document.createElement("div");
    p.textContent = text;
    el.appendChild(p);
  }
  const img = document.createElement("img");
  img.src = image;
  img.className = "attached-image";
  img.alt = "Attached image";
  el.appendChild(img);
}

function renderPlainOrAttachmentContent(el, content) {
  const match = content.match(ATTACHMENT_MARKER_RE);
  if (!match) {
    el.textContent = content;
    return;
  }
  const [, filename, fileText] = match;
  const typed = content.slice(0, match.index);
  el.textContent = "";
  if (typed) {
    const p = document.createElement("div");
    p.textContent = typed;
    el.appendChild(p);
  }
  const details = document.createElement("details");
  details.className = "attachment-chip";
  const summary = document.createElement("summary");
  summary.textContent = `📎 ${filename}`;
  const pre = document.createElement("pre");
  pre.textContent = fileText;
  details.appendChild(summary);
  details.appendChild(pre);
  el.appendChild(details);
}

function setMessageContent(el, role, content) {
  el.classList.remove("markdown-body");

  const imageContent = tryParseImageContent(content);
  if (imageContent) {
    renderImageContent(el, imageContent);
    return;
  }

  if (role === "assistant" && markdownReady) {
    el.classList.add("markdown-body");
    el.innerHTML = DOMPurify.sanitize(marked.parse(content));
    return;
  }

  renderPlainOrAttachmentContent(el, content);
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

function extractErrorMessage(raw) {
  // Backend/OpenRouter errors sometimes arrive as a raw JSON envelope, e.g.
  // {"error":{"message":"No endpoints found that support image input","code":404}} —
  // pull out the actual human-readable message if there is one.
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.error?.message) return parsed.error.message;
    if (typeof parsed?.error === "string") return parsed.error;
  } catch {
    // not JSON — raw is already a plain message
  }
  return raw;
}

function friendlyAttachmentError(message, attachment, chatHasImage) {
  const lower = message.toLowerCase();

  const missingVision =
    lower.includes("image") &&
    (lower.includes("no endpoints") || lower.includes("not support") || lower.includes("unsupported") || lower.includes("modality"));
  if (missingVision) {
    if (attachment?.kind === "image") {
      return "🖼️ This model can't see images. Pick a vision-capable model (e.g. a GPT-4o, Claude, or Gemini variant) from the dropdown and send again.";
    }
    if (chatHasImage) {
      // The current message has no image, but an earlier turn in this chat did —
      // full history gets resent every turn, so that old image is still what's tripping this up.
      return "🖼️ This model can't process images, and this conversation has one earlier in it. Switch to a vision-capable model, or start a new chat to leave the image out of the context.";
    }
    return "🖼️ This model doesn't support image input. Switch to a vision-capable model (e.g. a GPT-4o, Claude, or Gemini variant) and try again.";
  }

  const contextOverflow =
    lower.includes("context length") ||
    lower.includes("context_length") ||
    lower.includes("maximum context") ||
    lower.includes("token limit") ||
    lower.includes("too many tokens") ||
    lower.includes("too long");
  if (attachment?.kind === "text" && contextOverflow) {
    return attachment.fileType === "pdf"
      ? "📄 That PDF is too long for this model's context window. Try a shorter document, or switch to a model with a larger context length."
      : "📎 That file is too long for this model's context window. Try a shorter file, or switch to a model with a larger context length.";
  }

  return message;
}

function renderError(message) {
  clearEmptyState();
  const banner = document.createElement("div");
  banner.className = "error-banner";
  banner.textContent = message;
  messagesEl.appendChild(banner);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

let pendingAttachment = null; // {kind: "image", name, dataUrl} | {kind: "text", name, text}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function showAttachmentPreview({ name, thumb, loading, error }) {
  attachmentPreviewEl.hidden = false;
  attachmentPreviewEl.classList.toggle("error", !!error);
  attachmentPreviewEl.innerHTML = "";

  if (thumb) {
    const img = document.createElement("img");
    img.src = thumb;
    attachmentPreviewEl.appendChild(img);
  }

  const nameEl = document.createElement("span");
  nameEl.className = "name";
  nameEl.textContent = error ? error : loading ? `Reading ${name}…` : `📎 ${name}`;
  attachmentPreviewEl.appendChild(nameEl);

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "remove-btn";
  removeBtn.textContent = "✕";
  removeBtn.setAttribute("aria-label", "Remove attachment");
  removeBtn.addEventListener("click", clearAttachmentPreview);
  attachmentPreviewEl.appendChild(removeBtn);
}

function showAttachmentError(message) {
  pendingAttachment = null;
  showAttachmentPreview({ name: "", error: message });
}

function clearAttachmentPreview() {
  pendingAttachment = null;
  attachmentPreviewEl.hidden = true;
  attachmentPreviewEl.innerHTML = "";
}

attachBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  fileInput.value = "";
  if (!file) return;

  if (file.type.startsWith("image/")) {
    if (file.size > MAX_IMAGE_BYTES) {
      showAttachmentError(`Image too large (max ${MAX_IMAGE_BYTES / 1024 / 1024}MB).`);
      return;
    }
    try {
      const dataUrl = await readFileAsDataURL(file);
      pendingAttachment = { kind: "image", name: file.name, dataUrl };
      showAttachmentPreview({ name: file.name, thumb: dataUrl });
    } catch {
      showAttachmentError("Could not read image file.");
    }
    return;
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    showAttachmentError(`File too large (max ${MAX_UPLOAD_BYTES / 1024 / 1024}MB).`);
    return;
  }

  showAttachmentPreview({ name: file.name, loading: true });
  try {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/extract", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not read file.");
    const isPdf = file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf";
    pendingAttachment = { kind: "text", name: data.filename, text: data.text, fileType: isPdf ? "pdf" : "text" };
    showAttachmentPreview({ name: data.filename });
  } catch (err) {
    showAttachmentError(err.message);
  }
});

let allModels = [];
let freeOnly = localStorage.getItem("freeOnly") === "true";
freeOnlyToggle.checked = freeOnly;

function populateModelSelect() {
  const filtered = freeOnly ? allModels.filter((m) => m.is_free) : allModels;
  const current = modelSelect.value;
  modelSelect.innerHTML = "";

  if (filtered.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = "No free models available";
    opt.disabled = true;
    modelSelect.appendChild(opt);
    return;
  }

  for (const m of filtered) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.is_free ? `${m.name} (Free)` : m.name;
    modelSelect.appendChild(opt);
  }
  if (filtered.some((m) => m.id === current)) {
    modelSelect.value = current;
  }
}

async function loadModels() {
  try {
    const res = await fetch("/api/models");
    if (!res.ok) return; // keep the default option already in the select
    const models = await res.json();
    if (!Array.isArray(models) || models.length === 0) return;
    allModels = models;
    populateModelSelect();
  } catch (err) {
    console.warn("Could not load model list, using default.", err);
  }
}

freeOnlyToggle.addEventListener("change", () => {
  freeOnly = freeOnlyToggle.checked;
  localStorage.setItem("freeOnly", String(freeOnly));
  populateModelSelect();
});

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
    chatHasImage = chat.messages.some((m) => tryParseImageContent(m.content));
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
      chatHasImage = false;
      messagesEl.innerHTML = EMPTY_STATE_HTML;
    }
    renderChatList();
  } catch (err) {
    console.warn("Could not delete chat.", err);
  }
}

function startNewChat() {
  currentChatId = null;
  chatHasImage = false;
  messagesEl.innerHTML = EMPTY_STATE_HTML;
  renderChatList();
}

async function sendMessage(text) {
  const attachment = pendingAttachment;
  clearAttachmentPreview();

  let apiMessage = text;
  let apiImage = null;
  let displayContent = text;

  if (attachment?.kind === "image") {
    apiImage = attachment.dataUrl;
    displayContent = JSON.stringify({ text, image: attachment.dataUrl });
    chatHasImage = true;
  } else if (attachment?.kind === "text") {
    apiMessage = `${text}\n\n<!--attachment:${attachment.name}-->\n${attachment.text}\n<!--/attachment-->`;
    displayContent = apiMessage;
  }

  const now = new Date().toISOString();
  renderMessage("user", displayContent, now);

  const assistantMsg = renderMessage("assistant", "", now);
  const assistantEl = assistantMsg.contentEl;
  assistantEl.classList.add("streaming");

  sendBtn.disabled = true;
  let assistantText = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: modelSelect.value, message: apiMessage, image: apiImage, chat_id: currentChatId }),
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
            const fallbackTitle = attachment?.kind === "image" ? "📷 Image" : attachment ? `📎 ${attachment.name}` : "New chat";
            chats.unshift({
              id: parsed.chat_id,
              title: text.slice(0, 50) || fallbackTitle,
              model: modelSelect.value,
              updated_at: new Date().toISOString(),
            });
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
    const cleanMessage = extractErrorMessage(err.message);
    renderError(friendlyAttachmentError(cleanMessage, attachment, chatHasImage));
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
  if (!text && !pendingAttachment) return;
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
