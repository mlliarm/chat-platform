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

## 82540e2 — 2026-08-29 — replaced download thread as PDF and added hover text over delete and a pop-up check

### Changed
- The composer's PDF-export button icon replaced with a plain down-arrow
  "download" icon; its hover tooltip text is unchanged.

### Added
- Hover tooltip on each sidebar chat's ✕ delete button reading "DELETE !".
- A confirm dialog before a chat is actually deleted: "This action will
  delete the whole thread and it's irreversible. Are you sure?" — canceling
  leaves the chat untouched, confirming deletes it as before.

## f865bf4 — 2026-09-06 — Fix #3: stop leaking the OpenRouter API key in chat error messages

### Fixed
- A 402 (insufficient credits) or other non-200 response from OpenRouter's
  `chat/completions` endpoint was forwarded to the browser as-is, and its
  `error.message` can embed the account's key — showing up raw in the
  chat's error banner. Insufficient-credit errors now get a clean, friendly
  message instead (the raw error is still logged server-side), and any
  other upstream/network error has key-shaped substrings (`sk-...`)
  redacted before it reaches the client.

## ddd4de5 — 2026-09-06 — Fix #1: sanitize non-Latin chat titles in PDF export filenames

### Fixed
- Exporting a chat whose title was entirely non-Latin (e.g. Greek) crashed
  the server: the filename regex used `\w`, which is Unicode-aware by
  default, so those characters passed through unsanitized into the
  `Content-Disposition` header — and werkzeug's dev server encodes headers
  as latin-1, raising `UnicodeEncodeError`. The regex now matches ASCII
  word characters only, so any non-Latin title collapses to underscores
  like other unsafe characters already did.

## b5b3c75 — 2026-09-06 — Fix #2: reset model dropdown to default when starting a new chat

### Fixed
- Clicking "+ New chat" left the model dropdown on whatever model the
  previously viewed chat used instead of returning to the configured
  default. `startNewChat()` now resets the selection back to the
  server-provided default model (exposed via a `data-default-model`
  attribute on the `<select>`), unless that model has been filtered out
  of the current option list (e.g. by the "free only" toggle).

## dd0eca6 — 2026-09-06 — Add frontend test suite: Vitest unit tests + Playwright e2e tests

### Added
- A Vitest + jsdom unit tier (`npm run test:unit`) that loads the real
  `static/script.js` into a fresh jsdom realm per test — no refactor of the
  script needed, since its top-level `function` declarations attach to
  `window` when evaluated. Covers time formatting, error-message rewriting,
  image/attachment content parsing, markdown rendering, the full SSE
  streaming send flow (including rollback and chat-deleted edge cases), the
  model picker, chat list/CRUD, composer UI, and export-button state.
- A Playwright e2e tier (`npm run test:e2e`) that drives a real Chromium
  browser against a real Flask server (on its own port, with an isolated
  temp SQLite DB — the real `chat.db` is never touched) for page load,
  streaming send, image/file attachments, chat management (create, switch,
  pin, delete), model filtering, error banners, PDF export, and light/dark
  theming. `/api/chat` and `/api/models` are mocked at the network layer
  since they depend on OpenRouter; `/api/extract` hits the real Flask route.
- `npm test` runs both tiers; each subsequent frontend change should be run
  against this suite before committing.

## d60e2d3 — 2026-09-06 — Render LaTeX in assistant replies with MathJax

Closes #4.

### Added
- Assistant replies now render mathematical notation with MathJax v3
  (`tex-mml-chtml`, loaded from the same cdnjs origin as the other frontend
  libraries). Inline math is written `$…$` or `\(…\)`, display math `$$…$$`
  or `\[…\]`.
- A `marked` inline extension (`mathTokenizer()` in `static/script.js`)
  claims each math span as its own token before any other inline rule runs.
  This is what makes the feature work at all: markdown otherwise consumes
  the LaTeX before MathJax ever sees it — `\[`, `\{` and `\\` are markdown
  backslash escapes (so `\[…\]` delimiters and matrix/`aligned` row breaks
  silently vanish), and `_`/`*` inside an expression become emphasis tags.
  Owning the token leaves the expression body byte-for-byte intact; the
  renderer HTML-escapes it and re-emits it wrapped in
  `<span class="math-inline">`/`<span class="math-display">` using MathJax's
  configured `\(…\)`/`\[…\]` delimiters. A `span` (styled `display: block`)
  rather than a `div` keeps display math valid inside the `<p>` that marked
  wraps a paragraph in.
- Batched typesetting (`scheduleMathTypeset`, 60ms trailing window). The
  streaming render replaces the whole message body on every token, so an
  unbatched typeset would re-run MathJax once per token for the rest of a
  long reply and keep working through a backlog after the stream finished.
  Elements removed from the DOM before the flush (the error-rollback path)
  are dropped rather than typeset detached.
- MathJax loads `async`, so anything rendered before it is ready stays
  queued and is flushed by a `mathjax-ready` event dispatched from the
  loader's `pageReady` hook; `window.mathJaxPageReady` covers the race where
  MathJax finishes before `script.js` has registered its listener.

### Notes
- Only `\(…\)`/`\[…\]` are configured as MathJax delimiters, never `$`.
  Since every math span is re-emitted with those, MathJax never scans raw
  prose, so a bare `$5` in a sentence can't be misread as math. The single-`$`
  form is still accepted on input, guarded against currency by requiring a
  non-space after the opener, a non-space before the closer, and no digit
  after it.
- Math inside code spans and fenced code blocks is untouched: marked's
  codespan/code tokenizers consume those first, and MathJax skips `pre`/`code`
  by default.
- PDF export is unchanged — equations still export as their LaTeX source.

### Tests
- `tests/frontend/unit/math-rendering.test.js`: tokenizer delimiter cases,
  currency rejection, the `start()` offset marked needs to cut its text
  token, renderer escaping/delimiter output, and the typeset queue
  (pre-ready queuing, batching, no-math skip, detached-element drop).
- `tests/frontend/e2e/latex-rendering.spec.js`: real Chromium + real MathJax
  over a streamed reply — inline math, a multi-line `\begin{aligned}` block
  (asserting both rows survive, which is the regression a markdown-mangled
  `\\` would cause), math left literal in a code block, and currency in
  prose left untypeset.

## c85d704 — 2026-09-06 — hardening pass ahead of making the repo public

### Security
- The Werkzeug debugger no longer runs by default. `app.py`'s `__main__` block
  hardcoded `debug=True`, which serves an interactive Python console on any
  traceback — remote code execution for anyone who could reach the port. It is
  now opt-in via `FLASK_DEBUG`, and the bind address defaults to `127.0.0.1`
  (overridable with `HOST`/`PORT`) since the app has no auth or rate limiting
  and the OpenRouter key is held server-side.
- All six CDN assets in `templates/index.html` (marked, DOMPurify, highlight.js
  + its two themes, MathJax) now carry Subresource Integrity hashes plus
  `crossorigin`/`referrerpolicy`. DOMPurify is what sanitizes assistant Markdown
  before it becomes HTML, so a swapped file on the CDN would otherwise have
  silently removed that defense. Hashes are cdnjs's published sha512 values,
  verified byte-for-byte against the served files.

### Added
- `.github/workflows/ci.yml`: pytest + mypy on one job, Vitest + Playwright on
  another, both on push and PR. Needs no secrets — the backend suite mocks
  OpenRouter and the e2e suite intercepts it in the browser.
- README: a Security section describing the trust model and the existing
  defenses (key redaction, parameterized SQL, DOMPurify, upload caps), a
  License section naming GPL-3.0 and its copyleft obligation, an environment
  variable table, and a CI badge.
- `.env.example`: documented the optional `FLASK_DEBUG`, `HOST`, and `PORT`
  variables, commented out.

### Changed
- `playwright.config.js` reads `FLASK_BIN` (default `venv/bin/flask`), so CI
  can point the e2e web server at its own environment instead of the repo venv.

## 20542fb — 2026-09-06 — bump pinned GitHub Actions

### Changed
- Bumped the CI workflow's pinned actions to their current majors —
  `checkout@v4→v7`, `setup-python@v5→v7`, `setup-node@v4→v7`,
  `upload-artifact@v4→v7`. The first CI run passed but was annotated by
  GitHub: the v4/v5 majors target the deprecated Node.js 20 action runtime
  and were being force-run on Node 24. Every input in use (`python-version`,
  `node-version`, `cache`, `cache-dependency-path`, `name`, `path`,
  `retention-days`) exists unchanged in the new majors.
- Raised the Node version the frontend job tests against from 20 to 24.
  Node 20 reached end-of-life earlier this year, and 24 matches the version
  used locally.

## (pending) — 2026-09-06 — relicense from GPL-3.0 to AGPL-3.0

### Changed
- `LICENSE` replaced with the verbatim GNU Affero General Public License
  v3.0 (19 November 2007), retrieved from GitHub's licenses API and checked
  for completeness — all 17 sections, the `END OF TERMS AND CONDITIONS`
  terminator, and the appendix template.
- The practical difference is section 13, "Remote Network Interaction":
  plain GPL-3.0 triggers its copyleft obligation on *distribution* of the
  software, so someone could run a modified copy of this app as a hosted
  service without ever publishing their changes. AGPL-3.0 closes that gap —
  operating a modified version as a network service obliges the operator to
  offer its users the corresponding source. That maps to how this project
  is actually shaped: a web app whose likely derivative is a deployment
  rather than a redistribution.
- README's License section updated to describe the network-use obligation.

### Note
- Section 13's obligation falls on whoever runs a modified version publicly,
  not on this repository, so no source-offer link is required in the UI as
  shipped. Anyone deploying a fork for others to use will need to add one.

## 6b37e43 — 2026-09-06 — Render LaTeX in PDF export as images instead of raw source

Closes #5.

### Fixed
- PDF export now rasterizes LaTeX math into images instead of showing the
  raw source, matching the MathJax-rendered equations the browser has shown
  since d60e2d3. `markdown_pdf.py` pulls `\(…\)`/`\[…\]`/`$…$`/`$$…$$` spans
  out of the text before python-markdown sees them — mirroring the browser's
  `mathTokenizer()`, including leaving code spans and fenced code blocks
  untouched — then rasterizes each span with matplotlib's `mathtext` (no
  system LaTeX install required). Inline math is embedded via reportlab's
  Paragraph `<img>` tag sized to match the surrounding text; display math
  becomes its own centered paragraph.
- An expression `mathtext` can't parse (e.g. an `aligned`/`align`
  environment, which mathtext doesn't support) falls back to showing the
  raw LaTeX source in a monospace font rather than failing the export.

### Added
- `matplotlib` to `requirements.txt`, used only for its `mathtext` module
  (no system LaTeX/dvipng dependency).

### Tests
- `tests/test_markdown_pdf.py`: inline and display math rendering as images,
  currency `$5` not mistaken for math, math delimiters inside code spans/
  fenced blocks left untouched, and the mathtext-unsupported fallback path.
