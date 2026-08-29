import json
import os
import sys
import tempfile

# Safety net: redirect the DB path to a throwaway temp file *before* app.py
# (which calls db.init_db() at import time) or db.py get imported anywhere in
# the test session. Individual tests still isolate further via the `temp_db`
# fixture below, but this guarantees the real chat.db is never touched even
# by the first import.
os.environ.setdefault("CHAT_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="chat-platform-tests-"), "import-time.db"))
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import db as db_module
import app as app_module


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """Point db.py at a fresh, isolated SQLite file for the duration of one test."""
    db_path = str(tmp_path / "test_chat.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    yield db_module


@pytest.fixture
def client(temp_db, monkeypatch):
    """A Flask test client wired to the isolated test database with a fake API key set."""
    monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", "test-key")
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


class FakeGetResponse:
    """Mimics requests.Response for a plain (non-streaming) GET/POST call."""

    def __init__(self, status_code=200, json_data=None, text=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text if text is not None else json.dumps(self._json)

    def json(self):
        return self._json


class FakeStreamResponse:
    """Mimics requests.Response as used via `with requests.post(...) as upstream`."""

    def __init__(self, status_code=200, lines=None, text=""):
        self.status_code = status_code
        self._lines = lines or []
        self.text = text
        self.encoding = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line


def sse_lines_for_reply(chunks):
    """Builds OpenAI/OpenRouter-style SSE 'data: {...}' lines for a streamed assistant reply."""
    lines = [f'data: {json.dumps({"choices": [{"delta": {"content": chunk}}]})}' for chunk in chunks]
    lines.append("data: [DONE]")
    return lines
