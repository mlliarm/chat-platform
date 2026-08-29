# Local OpenRouter Chat

A minimal local chat app (Flask backend + vanilla JS frontend) that sends prompts
to any model available on [OpenRouter](https://openrouter.ai) and streams the
response back in a ChatGPT/Claude-style UI.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set OPENROUTER_API_KEY to your key (https://openrouter.ai/keys)
```

## Run

```bash
python app.py
```

Then open http://localhost:5000

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests never touch the real `chat.db` — `db.DB_PATH` is redirected to an
isolated temp file per test (see `tests/conftest.py`), and all OpenRouter
network calls are mocked, so no API key or network access is needed to run
the suite.

## Type checking

`app.py`, `db.py`, and the test suite are fully type-annotated.

```bash
pip install -r requirements-dev.txt
mypy
```

## How it works

- `app.py` — Flask server. `/api/models` proxies OpenRouter's model catalog to
  populate the picker; `/api/chat` takes just the chat id + the new user
  message, loads prior history from SQLite, forwards the full conversation to
  OpenRouter with `stream: true`, relays the SSE stream to the browser, and
  persists both the user message and the finished assistant reply once
  streaming ends. `/api/chats` (list/get/delete/pin) backs the sidebar.
  `/api/chats/<id>/export` renders the full conversation to a PDF for
  download — assistant replies are rendered from Markdown into formatted
  headings/lists/tables/code blocks (`markdown_pdf.py`, using `reportlab` +
  `Markdown`), not shown as raw Markdown syntax.
- `db.py` — tiny SQLite layer (`chat.db`, created automatically) storing
  `chats` and `messages`. A chat's title is auto-derived from its first
  message.
- `static/script.js` — reads the streamed response chunk by chunk and renders
  tokens as they arrive; loads/saves the sidebar's chat list against the
  `/api/chats` endpoints and switches the active conversation on click.
- `templates/index.html` + `static/style.css` — sidebar with past chats
  (click to reopen, ✕ to delete), a model selector, "New chat", plus a
  centered message list and composer, styled after Claude/ChatGPT.

## Notes

- Swap `DEFAULT_MODEL` in `.env` to any OpenRouter model id (e.g.
  `anthropic/claude-sonnet-4.5`, `openai/gpt-4o`, `google/gemini-2.0-flash-001`).
- This is boilerplate: no auth, no rate limiting. Add those before deploying
  anywhere beyond your own machine.
