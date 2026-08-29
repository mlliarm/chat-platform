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

## bf021fc — 2026-08-29 — fixed PDF rendering and APL/Greek

### Fixed
- A reasoning model's stray, unmatched `</think>` closing tag (left over from
  its chain-of-thought, with no opening tag) was passed through by Markdown
  as raw HTML, breaking the exporter's XML parser and silently falling back
  to one plain, unformatted paragraph for the whole message. `<think>...</think>`
  blocks and stray unmatched tags are now stripped before rendering.
- Accented Greek characters and several APL symbols (`⍳`, `⌽`, `⊂`, `⊃`, …)
  rendered as blank boxes in exported PDFs, because `reportlab`'s standard
  fonts only cover Latin-1. DejaVu Sans/Sans-Bold/Sans-Oblique/Sans-BoldOblique
  and DejaVu Sans Mono (bundled under `fonts/`, permissively licensed) are
  now used for every PDF-export style instead, covering Greek and most of
  the APL symbol range.

## c934cc6 — 2026-08-29 — added code block bubbles in PDF output too

### Fixed
- Fenced code blocks in exported PDFs showed as plain monospace text with no
  visible background — `reportlab`'s `Preformatted` flowable silently
  ignores `backColor`/border styling on its style, so the shaded "bubble"
  behind a code block was never actually drawn. Each code block is now
  wrapped in a `Table` cell styled with a background fill, border, and
  rounded corners, matching the browser's code block appearance.

## f3c7676 — 2026-08-29 — fixed minor issue with bullets not being rendered

### Fixed
- A dash/numbered list immediately following a paragraph or heading with no
  blank line in between (e.g. `**Explanation:**\n- item`) rendered as one
  paragraph with literal `-`/`1.` text instead of a bullet/numbered list.
  Unlike marked.js/CommonMark in the browser, python-markdown's parser won't
  let a list interrupt a paragraph without a blank line separating them. A
  blank line is now inserted before such a list before conversion — scoped
  narrowly (zero-indent list marker directly after zero-indent, non-list
  text) so it doesn't affect wrapped continuation lines inside an existing
  list item, nested list items, or a `- `-looking line inside a fenced code
  block.

## 42e6607 — 2026-08-29 — added syntax highlight in the UI frontend

### Added
- Syntax highlighting for fenced code blocks in assistant replies, via
  `highlight.js` (loaded from CDN). `marked`'s code-block renderer now runs
  `hljs.highlight()` using the fence's language hint (e.g. `` ```python ``),
  falling back to `hljs.highlightAuto()` when there's no hint or the
  language isn't recognized; if `highlight.js` fails to load, code still
  renders, just unhighlighted.
- Light/dark `highlight.js` theme CSS swapped automatically via
  `prefers-color-scheme`, matching the app's existing dark-mode handling;
  the theme's own box background/padding is overridden so highlighted code
  sits inside the app's existing purple code-block "bubble" instead of
  nesting a second box.

## 38722bf — 2026-08-29 — added syntax highlight with pygments in pdf export

### Added
- Syntax highlighting for fenced code blocks in exported PDFs, via
  `Pygments`, so the coloring already shown in the browser (`highlight.js`)
  persists in the PDF instead of code showing as plain monospace text.
  Uses the fence's language hint, falling back to auto-detection when
  there's none or it's unrecognized (e.g. APL, which Pygments has no
  dedicated lexer for) — verified across 11 languages in a real chat.
- Code blocks now render via reportlab's `XPreformatted` (a `Paragraph`
  subclass) instead of plain `Preformatted`, since only `XPreformatted`
  supports colored `<font>` spans while still preserving exact monospace
  line/whitespace layout — including a color span that itself spans
  multiple lines (e.g. a multi-line string or comment).

### Fixed
- Pygments' lexers commonly append a trailing newline internally for
  correct tokenization even when the input code doesn't end with one; this
  was introducing a spurious blank line at the end of highlighted code
  blocks. The lexer's appended newline is now trimmed back off before
  rendering.
