import json
import os
import sys
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import ModuleType, TracebackType
from typing import Any

# Safety net: redirect the DB path to a throwaway temp file *before* app.py
# (which calls db.init_db() at import time) or db.py get imported anywhere in
# the test session. Individual tests still isolate further via the `temp_db`
# fixture below, but this guarantees the real chat.db is never touched even
# by the first import.
os.environ.setdefault("CHAT_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="chat-platform-tests-"), "import-time.db"))
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask.testing import FlaskClient

import db as db_module
import app as app_module


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[ModuleType]:
    """Point db.py at a fresh, isolated SQLite file for the duration of one test."""
    db_path = str(tmp_path / "test_chat.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    yield db_module


@pytest.fixture
def client(temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch) -> Iterator[FlaskClient]:
    """A Flask test client wired to the isolated test database with a fake API key set."""
    monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", "test-key")
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


class FakeGetResponse:
    """Mimics requests.Response for a plain (non-streaming) GET/POST call."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._json: dict[str, Any] = json_data if json_data is not None else {}
        self.text = text if text is not None else json.dumps(self._json)

    def json(self) -> dict[str, Any]:
        return self._json


class FakeStreamResponse:
    """Mimics requests.Response as used via `with requests.post(...) as upstream`."""

    def __init__(self, status_code: int = 200, lines: Iterable[str] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._lines: Iterable[str] = lines if lines is not None else []
        self.text = text
        self.encoding: str | None = None

    def __enter__(self) -> "FakeStreamResponse":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = True) -> Iterator[str]:
        for line in self._lines:
            yield line


def sse_lines_for_reply(chunks: list[str]) -> list[str]:
    """Builds OpenAI/OpenRouter-style SSE 'data: {...}' lines for a streamed assistant reply."""
    lines = [f'data: {json.dumps({"choices": [{"delta": {"content": chunk}}]})}' for chunk in chunks]
    lines.append("data: [DONE]")
    return lines
