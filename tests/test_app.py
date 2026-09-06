"""Tests for app.py — Flask routes, streaming, attachments, and the
rollback-on-failure logic.

Network calls to OpenRouter are always mocked (via monkeypatching
app.requests.get / app.requests.post) — no real HTTP calls are made and no
real API key is required. Every test runs against an isolated temp SQLite
file (see the `client`/`temp_db` fixtures in conftest.py); the real chat.db
is never touched.
"""

import io
import json
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest
import requests
from flask.testing import FlaskClient

import app as app_module
from conftest import FakeGetResponse, FakeStreamResponse, sse_lines_for_reply

TINY_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
    "2mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def parse_sse(body_text: str) -> list[dict[str, Any]]:
    """Parses raw 'data: {...}' SSE text into a list of decoded JSON payloads."""
    events: list[dict[str, Any]] = []
    for chunk in body_text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk.startswith("data:"):
            continue
        data = chunk[len("data:"):].strip()
        if data == "[DONE]":
            continue
        events.append(json.loads(data))
    return events


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


def test_index_renders_with_default_model(client: FlaskClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"openai/gpt-4o-mini" in resp.data


# ---------------------------------------------------------------------------
# GET /api/models
# ---------------------------------------------------------------------------


def test_list_models_without_api_key_returns_500(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", None)
    resp = client.get("/api/models")
    assert resp.status_code == 500
    assert "error" in (resp.get_json() or {})


def test_list_models_classifies_free_and_sorts(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_data = {
        "data": [
            {"id": "b/paid", "name": "Bravo", "context_length": 4096, "pricing": {"prompt": "0.001", "completion": "0.002"}},
            {"id": "a/free", "name": "Alpha", "context_length": 8192, "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "c/no-pricing", "name": "Charlie", "context_length": 2048, "pricing": {}},
        ]
    }
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: FakeGetResponse(200, fake_data))

    resp = client.get("/api/models")
    assert resp.status_code == 200
    models = resp.get_json()

    assert [m["name"] for m in models] == ["Alpha", "Bravo", "Charlie"]  # sorted case-insensitively
    by_id = {m["id"]: m for m in models}
    assert by_id["a/free"]["is_free"] is True
    assert by_id["b/paid"]["is_free"] is False
    assert by_id["c/no-pricing"]["is_free"] is False  # missing pricing must not be misread as free


def test_list_models_upstream_failure_propagates_status(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: FakeGetResponse(503, text="upstream down"))
    resp = client.get("/api/models")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/extract
# ---------------------------------------------------------------------------


def test_extract_no_file_returns_400(client: FlaskClient) -> None:
    resp = client.post("/api/extract", data={})
    assert resp.status_code == 400


def test_extract_plain_text_file(client: FlaskClient) -> None:
    from io import BytesIO

    data = {"file": (BytesIO(b"Hello, this is a test file."), "notes.txt")}
    resp = client.post("/api/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filename"] == "notes.txt"
    assert body["text"] == "Hello, this is a test file."


def test_extract_unsupported_binary_file_returns_400(client: FlaskClient) -> None:
    from io import BytesIO

    data = {"file": (BytesIO(bytes(range(256))), "weird.bin")}
    resp = client.post("/api/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in (resp.get_json() or {})


def test_extract_truncates_long_text(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    monkeypatch.setattr(app_module, "MAX_ATTACHMENT_CHARS", 100)
    long_text = "x" * 500
    data = {"file": (BytesIO(long_text.encode()), "big.txt")}
    resp = client.post("/api/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["text"]) <= 100 + len("\n\n[...truncated...]")
    assert body["text"].endswith("[...truncated...]")


def test_extract_pdf_with_text(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    class FakePage:
        def extract_text(self) -> str:
            return "Real extracted PDF text."

    class FakeReader:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.pages = [FakePage()]

    monkeypatch.setattr(app_module, "PdfReader", FakeReader)
    data = {"file": (BytesIO(b"%PDF-fake-bytes"), "doc.pdf")}
    resp = client.post("/api/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert (resp.get_json() or {})["text"] == "Real extracted PDF text."


def test_extract_pdf_with_no_text_returns_400(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    class FakePage:
        def extract_text(self) -> str:
            return ""

    class FakeReader:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.pages = [FakePage()]

    monkeypatch.setattr(app_module, "PdfReader", FakeReader)
    data = {"file": (BytesIO(b"%PDF-fake-bytes"), "scanned.pdf")}
    resp = client.post("/api/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    error = (resp.get_json() or {})["error"].lower()
    assert "scanned" in error or "extractable" in error


def test_extract_pdf_reader_error_returns_400(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    class ExplodingReader:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise ValueError("corrupt PDF")

    monkeypatch.setattr(app_module, "PdfReader", ExplodingReader)
    data = {"file": (BytesIO(b"not really a pdf"), "bad.pdf")}
    resp = client.post("/api/extract", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/chats (list / get / delete)
# ---------------------------------------------------------------------------


def test_chats_list_empty(client: FlaskClient) -> None:
    resp = client.get("/api/chats")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_chats_list_and_get(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Hi there", model="openai/gpt-4o-mini")
    temp_db.add_message(chat_id, "user", "hello")

    listed = client.get("/api/chats").get_json()
    assert len(listed) == 1
    assert listed[0]["id"] == chat_id
    assert listed[0]["title"] == "Hi there"

    detail = client.get(f"/api/chats/{chat_id}").get_json()
    assert detail["id"] == chat_id
    assert detail["messages"] == [{"role": "user", "content": "hello", "created_at": detail["messages"][0]["created_at"]}]


def test_chats_get_missing_returns_404(client: FlaskClient) -> None:
    resp = client.get("/api/chats/does-not-exist")
    assert resp.status_code == 404


def test_chats_delete(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Bye", model="m")
    resp = client.delete(f"/api/chats/{chat_id}")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert temp_db.chat_exists(chat_id) is False


# ---------------------------------------------------------------------------
# POST /api/chats/<id>/pin
# ---------------------------------------------------------------------------


def test_pin_chat_moves_it_to_top_of_list(client: FlaskClient, temp_db: ModuleType) -> None:
    older_id = temp_db.create_chat(title="Older", model="m")
    temp_db.create_chat(title="Newer", model="m")  # more recently updated, would normally sort first

    resp = client.post(f"/api/chats/{older_id}/pin", json={"pinned": True})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "pinned": True}

    listed = client.get("/api/chats").get_json()
    assert listed[0]["id"] == older_id
    assert listed[0]["pinned"] is True
    assert listed[1]["pinned"] is False


def test_unpin_chat(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    temp_db.set_pinned(chat_id, True)

    resp = client.post(f"/api/chats/{chat_id}/pin", json={"pinned": False})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "pinned": False}
    assert client.get("/api/chats").get_json()[0]["pinned"] is False


def test_pin_defaults_to_true_when_no_body_sent(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    resp = client.post(f"/api/chats/{chat_id}/pin")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "pinned": True}


def test_pin_nonexistent_chat_returns_404(client: FlaskClient) -> None:
    resp = client.post("/api/chats/does-not-exist/pin", json={"pinned": True})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/chats/<id>/export
# ---------------------------------------------------------------------------

# A valid 1x1 transparent PNG, as a data: URL, for exercising image messages.
ONE_PX_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA"
    "C0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_export_missing_chat_returns_404(client: FlaskClient) -> None:
    resp = client.get("/api/chats/does-not-exist/export")
    assert resp.status_code == 404


def test_export_returns_pdf_with_attachment_headers(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Weekend trip?", model="openai/gpt-4o-mini")
    temp_db.add_message(chat_id, "user", "hello")

    resp = client.get(f"/api/chats/{chat_id}/export")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "Weekend_trip.pdf" in resp.headers["Content-Disposition"]
    assert resp.data[:5] == b"%PDF-"


def test_export_includes_title_and_plain_messages(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Recipe ideas", model="openai/gpt-4o-mini")
    temp_db.add_message(chat_id, "user", "What can I cook with eggplant?")
    temp_db.add_message(chat_id, "assistant", "Try a baba ganoush.")

    resp = client.get(f"/api/chats/{chat_id}/export")
    text = _pdf_text(resp.data)
    assert "Recipe ideas" in text
    assert "What can I cook with eggplant?" in text
    assert "Try a baba ganoush." in text
    assert "You" in text
    assert "Assistant" in text


def test_export_includes_text_attachment_marker(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Notes", model="m")
    temp_db.add_message(
        chat_id,
        "user",
        "Summarize this\n\n<!--attachment:notes.txt-->\nsome extracted file text\n<!--/attachment-->",
    )

    resp = client.get(f"/api/chats/{chat_id}/export")
    text = _pdf_text(resp.data)
    assert "Summarize this" in text
    assert "notes.txt" in text


def test_export_includes_image_message_without_erroring(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Photo", model="m")
    temp_db.add_message(chat_id, "user", json.dumps({"text": "check this out", "image": ONE_PX_PNG}))

    resp = client.get(f"/api/chats/{chat_id}/export")
    assert resp.status_code == 200
    assert resp.data[:5] == b"%PDF-"
    text = _pdf_text(resp.data)
    assert "check this out" in text


def test_export_filename_strips_unsafe_characters(client: FlaskClient, temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title='Weird "title"/with:chars?', model="m")
    resp = client.get(f"/api/chats/{chat_id}/export")
    disposition = resp.headers["Content-Disposition"]
    assert '"' not in disposition.split("filename=")[1][1:-1]
    assert "/" not in disposition


# ---------------------------------------------------------------------------
# POST /api/chat — validation
# ---------------------------------------------------------------------------


def test_chat_without_api_key_returns_500(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", None)
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 500


def test_chat_empty_message_no_image_returns_400(client: FlaskClient) -> None:
    resp = client.post("/api/chat", json={"message": "   ", "chat_id": None})
    assert resp.status_code == 400


def test_chat_invalid_image_url_returns_400(client: FlaskClient) -> None:
    resp = client.post("/api/chat", json={"message": "hi", "image": "not-a-data-url"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/chat — successful flow
# ---------------------------------------------------------------------------


def test_chat_success_streams_reply_and_persists_both_messages(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_upstream = FakeStreamResponse(200, sse_lines_for_reply(["Hello", " world"]))
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: fake_upstream)

    resp = client.post("/api/chat", json={"message": "Hi model", "model": "openai/gpt-4o-mini", "chat_id": None})
    assert resp.status_code == 200
    events = parse_sse(resp.get_data(as_text=True))

    assert events[0]["is_new_chat"] is True
    chat_id = events[0]["chat_id"]

    deltas = [e["choices"][0]["delta"]["content"] for e in events if "choices" in e]
    assert deltas == ["Hello", " world"]

    chat = temp_db.get_chat(chat_id)
    assert chat["title"] == "Hi model"
    assert [(m["role"], m["content"]) for m in chat["messages"]] == [
        ("user", "Hi model"),
        ("assistant", "Hello world"),
    ]

    # The UTF-8 mojibake fix: encoding must always be forced explicitly.
    assert fake_upstream.encoding == "utf-8"


def test_chat_continues_existing_chat_with_full_history(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = temp_db.create_chat(title="Existing", model="openai/gpt-4o-mini")
    temp_db.add_message(chat_id, "user", "first turn")
    temp_db.add_message(chat_id, "assistant", "first reply")

    captured_payload: dict[str, Any] = {}

    def fake_post(
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        stream: bool | None = None,
        timeout: int | None = None,
    ) -> FakeStreamResponse:
        assert json is not None
        captured_payload["messages"] = json["messages"]
        return FakeStreamResponse(200, sse_lines_for_reply(["ok"]))

    monkeypatch.setattr(app_module.requests, "post", fake_post)

    resp = client.post("/api/chat", json={"message": "second turn", "chat_id": chat_id})
    assert resp.status_code == 200
    events = parse_sse(resp.get_data(as_text=True))
    assert events[0]["is_new_chat"] is False
    assert events[0]["chat_id"] == chat_id

    # The full prior history must have been replayed to the model.
    assert captured_payload["messages"] == [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second turn"},
    ]


def test_chat_with_nonexistent_chat_id_creates_a_new_chat(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(200, sse_lines_for_reply(["hi"])))
    resp = client.post("/api/chat", json={"message": "hello", "chat_id": "totally-bogus-id"})
    events = parse_sse(resp.get_data(as_text=True))
    assert events[0]["is_new_chat"] is True
    assert events[0]["chat_id"] != "totally-bogus-id"


# ---------------------------------------------------------------------------
# POST /api/chat — image attachments
# ---------------------------------------------------------------------------


def test_chat_image_only_message_gets_image_title_and_json_storage(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(200, sse_lines_for_reply(["I see a cat"])))

    resp = client.post("/api/chat", json={"message": "", "image": TINY_PNG, "chat_id": None})
    events = parse_sse(resp.get_data(as_text=True))
    chat_id = events[0]["chat_id"]

    chat = temp_db.get_chat(chat_id)
    assert chat["title"] == "📷 Image"

    stored = json.loads(chat["messages"][0]["content"])
    assert stored == {"text": "", "image": TINY_PNG}


def test_chat_image_is_converted_to_vision_content_blocks(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload: dict[str, Any] = {}

    def fake_post(
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        stream: bool | None = None,
        timeout: int | None = None,
    ) -> FakeStreamResponse:
        assert json is not None
        captured_payload["messages"] = json["messages"]
        return FakeStreamResponse(200, sse_lines_for_reply(["ok"]))

    monkeypatch.setattr(app_module.requests, "post", fake_post)

    resp = client.post("/api/chat", json={"message": "what is this?", "image": TINY_PNG, "chat_id": None})
    resp.get_data()  # force the streaming generator to run to completion

    sent = captured_payload["messages"][-1]
    assert sent["role"] == "user"
    assert sent["content"] == [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": TINY_PNG}},
    ]


def test_chat_image_from_history_is_replayed_as_vision_block(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = temp_db.create_chat(title="Img chat", model="m")
    temp_db.add_message(chat_id, "user", json.dumps({"text": "look", "image": TINY_PNG}))
    temp_db.add_message(chat_id, "assistant", "I see it")

    captured_payload: dict[str, Any] = {}

    def fake_post(
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        stream: bool | None = None,
        timeout: int | None = None,
    ) -> FakeStreamResponse:
        assert json is not None
        captured_payload["messages"] = json["messages"]
        return FakeStreamResponse(200, sse_lines_for_reply(["ok"]))

    monkeypatch.setattr(app_module.requests, "post", fake_post)
    resp = client.post("/api/chat", json={"message": "follow up", "chat_id": chat_id})
    resp.get_data()

    first_message = captured_payload["messages"][0]
    assert first_message["content"] == [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": TINY_PNG}},
    ]


# ---------------------------------------------------------------------------
# POST /api/chat — text/PDF attachment folding (title stripping)
# ---------------------------------------------------------------------------


def test_chat_title_strips_attachment_marker_when_text_present(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(200, sse_lines_for_reply(["ok"])))
    message = "Please summarize this\n\n<!--attachment:notes.txt-->\nThe quick brown fox.\n<!--/attachment-->"

    resp = client.post("/api/chat", json={"message": message, "chat_id": None})
    chat_id = parse_sse(resp.get_data(as_text=True))[0]["chat_id"]

    chat = temp_db.get_chat(chat_id)
    assert chat["title"] == "Please summarize this"
    assert chat["messages"][0]["content"] == message  # full content (with marker) preserved for the model/history


def test_chat_title_falls_back_to_filename_when_no_typed_text(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(200, sse_lines_for_reply(["ok"])))
    message = "\n\n<!--attachment:report.pdf-->\nSome extracted PDF content.\n<!--/attachment-->"

    resp = client.post("/api/chat", json={"message": message, "chat_id": None})
    chat_id = parse_sse(resp.get_data(as_text=True))[0]["chat_id"]

    chat = temp_db.get_chat(chat_id)
    assert chat is not None
    assert chat["title"] == "📎 report.pdf"


# ---------------------------------------------------------------------------
# POST /api/chat — rollback on failure
# ---------------------------------------------------------------------------


def test_chat_failure_on_brand_new_chat_deletes_the_whole_chat(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    error_body = '{"error":{"message":"No endpoints found that support image input","code":404}}'
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(404, text=error_body))

    before = len(temp_db.list_chats())
    resp = client.post("/api/chat", json={"message": "", "image": TINY_PNG, "chat_id": None})
    events = parse_sse(resp.get_data(as_text=True))

    error_event = events[-1]
    assert error_event["rolled_back"] is True
    assert error_event["chat_deleted"] is True

    after = len(temp_db.list_chats())
    assert after == before  # no ghost chat left behind


def test_chat_failure_on_existing_chat_only_rolls_back_the_new_message(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = temp_db.create_chat(title="Existing", model="m")
    temp_db.add_message(chat_id, "user", "real first message")
    temp_db.add_message(chat_id, "assistant", "real reply")

    error_body = '{"error":{"message":"No endpoints found that support image input","code":404}}'
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(404, text=error_body))

    resp = client.post("/api/chat", json={"message": "", "image": TINY_PNG, "chat_id": chat_id})
    events = parse_sse(resp.get_data(as_text=True))
    error_event = events[-1]
    assert error_event["rolled_back"] is True
    assert "chat_deleted" not in error_event

    # The chat and its original two messages must survive untouched.
    assert temp_db.chat_exists(chat_id) is True
    history = temp_db.get_history(chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "real first message"),
        ("assistant", "real reply"),
    ]


def test_chat_failure_leaves_no_trace_in_next_turns_history(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact bug scenario: a rejected image must not poison a later plain-text turn."""
    chat_id = temp_db.create_chat(title="Existing", model="m")
    temp_db.add_message(chat_id, "user", "hello")
    temp_db.add_message(chat_id, "assistant", "hi there")

    error_body = '{"error":{"message":"No endpoints found that support image input","code":404}}'
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(404, text=error_body))
    client.post("/api/chat", json={"message": "", "image": TINY_PNG, "chat_id": chat_id}).get_data()

    captured_payload: dict[str, Any] = {}

    def fake_post_success(
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        stream: bool | None = None,
        timeout: int | None = None,
    ) -> FakeStreamResponse:
        assert json is not None
        captured_payload["messages"] = json["messages"]
        return FakeStreamResponse(200, sse_lines_for_reply(["ok"]))

    monkeypatch.setattr(app_module.requests, "post", fake_post_success)
    client.post("/api/chat", json={"message": "just a plain follow-up", "chat_id": chat_id}).get_data()

    # No image content block anywhere in what got sent to the model this time.
    for msg in captured_payload["messages"]:
        assert not (isinstance(msg["content"], list))


# ---------------------------------------------------------------------------
# POST /api/chat — issue #3: upstream errors must never leak the API key
# ---------------------------------------------------------------------------


def test_chat_insufficient_credits_returns_friendly_message_without_key(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact bug from issue #3: a 402 from OpenRouter must not surface the raw key."""
    leaked_key = "sk-or-v1-f2912345secretkeystufff00c15"
    error_body = json.dumps(
        {
            "error": {
                "message": (
                    f"This request requires more credits, or fewer max_tokens. "
                    f"Your key ({leaked_key}) has 0 credits remaining."
                ),
                "code": 402,
            }
        }
    )
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(402, text=error_body))

    resp = client.post("/api/chat", json={"message": "hi", "chat_id": None})
    raw = resp.get_data(as_text=True)

    assert leaked_key not in raw
    events = parse_sse(raw)
    error_event = events[-1]
    assert error_event["rolled_back"] is True
    assert "credits" in json.loads(error_event["error"])["error"]["message"].lower()


def test_chat_upstream_error_redacts_leaked_key_for_other_status_codes(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defense-in-depth: any status code with a key-shaped string gets it stripped."""
    leaked_key = "sk-or-v1-f2912345secretkeystufff00c15"
    error_body = json.dumps({"error": {"message": f"Internal error for key {leaked_key}", "code": 500}})
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: FakeStreamResponse(500, text=error_body))

    resp = client.post("/api/chat", json={"message": "hi", "chat_id": None})
    raw = resp.get_data(as_text=True)

    assert leaked_key not in raw
    assert "[redacted]" in raw
    assert "Internal error for key" in raw


def test_chat_connection_error_before_any_content_rolls_back(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_connection_error(*a: Any, **k: Any) -> FakeStreamResponse:
        raise requests.exceptions.ConnectionError("network is down")

    monkeypatch.setattr(app_module.requests, "post", raise_connection_error)

    before = len(temp_db.list_chats())
    resp = client.post("/api/chat", json={"message": "hello", "chat_id": None})
    events = parse_sse(resp.get_data(as_text=True))
    assert events[-1]["rolled_back"] is True
    assert len(temp_db.list_chats()) == before


def test_chat_connection_error_after_partial_content_is_kept(
    client: FlaskClient, temp_db: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def partial_then_raise() -> Iterator[str]:
        yield 'data: {"choices":[{"delta":{"content":"Partial answer"}}]}'
        raise requests.exceptions.ConnectionError("connection reset mid-stream")

    fake_upstream = FakeStreamResponse(200, partial_then_raise())
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **k: fake_upstream)

    resp = client.post("/api/chat", json={"message": "hello", "chat_id": None})
    events = parse_sse(resp.get_data(as_text=True))

    chat_id = events[0]["chat_id"]
    error_event = events[-1]
    assert "rolled_back" not in error_event  # partial content already came through — don't discard it

    chat = temp_db.get_chat(chat_id)
    assert chat is not None
    assert [(m["role"], m["content"]) for m in chat["messages"]] == [
        ("user", "hello"),
        ("assistant", "Partial answer"),
    ]
