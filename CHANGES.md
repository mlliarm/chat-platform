# Changes

A chronological log of features and fixes for this project, one section per
commit. Oldest first — new entries are appended at the bottom each time a new
commit is made.

## b5b9333 — 2026-08-28 — Initial commit

- Repository initialized with the project's LICENSE.

## d83a0c5 — 2026-08-28 — basic working boilerplate

### Added
- Flask backend proxying chat completions to OpenRouter, streamed to the browser via Server-Sent Events.
- Chat UI in the style of Claude/ChatGPT: sidebar, model dropdown populated live from OpenRouter's model catalog, composer with token-by-token streaming render.
- SQLite persistence (`db.py`): `chats`/`messages` tables, full conversation history replayed to the model on every turn, sidebar listing past chats (click to reopen, ✕ to delete), auto-generated chat titles from the first message.
- Per-message and per-chat timestamps: absolute time under each bubble, relative "Xm/h/d ago" labels in the sidebar that self-refresh.

### Fixed
- Forced UTF-8 decoding on the OpenRouter SSE stream (`upstream.encoding = "utf-8"`). Without it, `requests` fell back to Latin-1 per the HTTP spec default (no `charset` on the stream's `Content-Type`), and multi-byte characters — accented Latin, Greek, CJK, emoji — rendered as mojibake.

## f6e44a6 — 2026-08-28 — added history in chats

### Added
- Assistant replies rendered as sanitized Markdown (`marked` + `DOMPurify`):
  headings, lists, bold/italic, links (opened in a new tab), tables, and
  fenced code blocks. User messages stay plain text; if the CDN libraries
  fail to load, replies fall back safely to plain text instead of raw HTML.

## 068bfce — 2026-08-28 — added cats !

### Added
- Light purple/lavender visual theme (with a matching dark-mode variant),
  accent color shifted to violet.
- Cat mascot: 🐱 in the header next to the "Local LLM ChAT" title (title
  capitalized to spell out CAT), plus a large, ~90%-transparent watermark
  cat centered behind the chat window.

## fdf6b16 — 2026-08-28 — added free models toggle

### Added
- Toggle switch next to the "Model" label that filters the dropdown to
  free-tier OpenRouter models only, detected via `pricing.prompt == 0` and
  `pricing.completion == 0`. Preference persisted in `localStorage`.

## 13d2ae3 — 2026-08-28 — added support for txt, PDF, image attachments

### Added
- 📎 attach button next to the composer, supporting plain text/code files,
  PDFs, and images.
- Text/PDF files are extracted server-side (`POST /api/extract`, using
  `pypdf` for PDFs) and folded into the message behind a collapsible
  "📎 filename" chip — this works with any model since it's just text.
- Images are sent as proper multimodal content (base64 `image_url` blocks)
  to vision-capable models and persisted so they stay part of the
  conversation across later turns.
- Guardrails: 8MB image cap, 10MB upload cap, and a 30,000-character
  truncation limit on extracted text to protect the model's context window.

## c12f57c — 2026-08-28 — better error handling when model doesn't support images

### Added
- Friendly, specific error messages in place of raw OpenRouter JSON:
  distinct wording for "this model can't see images," "PDF too long for
  this model's context window," and "file too long for this model's context
  window" — matched against the actual upstream error text so an unrelated
  failure (bad API key, rate limit) is never mislabeled.
- Error detection extended to recognize when the *current* message has no
  image but an *earlier* turn in the same chat did (since full history is
  replayed every turn), so the message correctly explains the real cause
  instead of a confusing "no image here" mismatch.

## dcbf374 — 2026-08-28 — fixed corner case where failed image parse poisoned discussion

### Fixed
- The backend was saving a user's message to the database *before* calling
  OpenRouter. A rejected message (e.g. an image sent to a non-vision model)
  stayed permanently in that chat's history and kept poisoning every later
  turn — even plain text ones — since full history gets replayed on each
  request. Fixed by rolling the failed message back out of the database:
  the whole (now-empty) chat is deleted if it was a brand-new chat's first
  message, or just the one bad message is removed if the chat already had
  other history. The frontend's local "this chat has an image" tracking is
  reverted in lockstep so it doesn't stay stuck pointing at an image that no
  longer exists.

## 799cf21 — 2026-08-29 — added tests on app.py and db.py methods and functions

### Added
- Full `pytest` suite (`tests/`) covering `db.py` (CRUD, cascade deletes,
  ordering) and `app.py` (routes, streaming, attachments, the rollback
  logic) — 45 tests. All OpenRouter network calls are mocked, and the
  database is isolated per test via a `CHAT_DB_PATH` override so the real
  `chat.db` is never touched, even at import time.
- `db.DB_PATH` made overridable via the `CHAT_DB_PATH` environment variable
  to support this isolation — the one production-code change needed for
  real test isolation, fully backward-compatible (defaults unchanged).

## a1d579a — 2026-08-29 — added type annotations and tested against mypy

### Added
- Full type annotations across `app.py`, `db.py`, and the test suite, plus
  a `mypy.ini` config (`disallow_untyped_defs`, `check_untyped_defs`,
  `warn_return_any`).

### Fixed
- A latent looseness in `POST /api/chat`: the `chat_id` from the request
  body wasn't validated as a string before use. Now explicitly checked with
  `isinstance` and properly narrowed.
- A real bug in the test double `FakeStreamResponse.__exit__`, caught by
  mypy: it was declared to return `bool` but always returned `False` —
  fixed to return `None`, the correct "don't suppress exceptions" contract.

## 5f7cfe3 — 2026-08-29 — added pin chat tab feature

### Added
- ⭐ pin button on each sidebar chat, to the left of the title: click to
  pin — turns into a filled yellow star and sorts the chat to the top of
  the list regardless of recency; click again to unpin.
- New `POST /api/chats/<id>/pin` endpoint; a `pinned` column added to the
  `chats` table with a safe, automatic in-place migration
  (`ALTER TABLE ... ADD COLUMN`) that runs on startup and preserves all
  existing chats/messages — verified against both a synthetic
  pre-migration database and the real `chat.db`.

## 100521a — 2026-08-29 — documented all changes so far, fixes and features implemented

### Added
- This `CHANGES.md` file: a chronological, one-section-per-commit log of
  every feature and fix in the project, reconstructed from git history plus
  conversation history.

## bb403df — 2026-08-29 — added PDF export of chat feature

### Added
- 📄 PDF export button in the composer, to the left of the attach button
  (enabled only once a chat is open): downloads the open conversation as a
  PDF via a new `GET /api/chats/<id>/export` endpoint.
- PDF built with `reportlab`: chat title, model, and each message with a
  friendly formatted timestamp (`Aug 29, 2026, 09:01 AM`); attachment names
  shown as a `📎 filename` note; attached images decoded from their stored
  base64 data URL and embedded inline, scaled to fit the page.
- 6 new tests: missing-chat 404, `Content-Disposition`/mimetype headers,
  filename sanitization, plain-text and attachment-marker messages, and
  image messages.

## 9660dbe — 2026-08-29 — fixed issue of markdown not rendered in PDF output

### Fixed
- Assistant replies in exported PDFs showed raw Markdown syntax (literal
  `**bold**`, `# Heading`, `` `code` ``, etc.) instead of rendered
  formatting.

### Added
- New `markdown_pdf.py` module: converts an assistant message's Markdown
  into `reportlab` flowables — bold/italic/inline code, headings (h1–h6, in
  distinct sizes), bulleted and ordered lists (including nested block
  content), fenced code blocks (monospace, shaded background), tables
  (styled header row), blockquotes, clickable colored links, and horizontal
  rules — mirroring the `marked.js` rendering already used in the browser.
  User messages keep rendering as plain text, unchanged.
- 11 new tests for the Markdown-to-PDF renderer, covering each construct
  above plus a malformed-HTML fallback path.
