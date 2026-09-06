import base64
import io
import json
import os
import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from flask.typing import ResponseReturnValue
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable, Image as RLImage, Paragraph, SimpleDocTemplate

import db
from markdown_pdf import FONT_BOLD, FONT_REGULAR, markdown_flowables

load_dotenv()
db.init_db()

OPENROUTER_API_KEY: str | None = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Shown in the app's own HTTP headers to OpenRouter (their leaderboard/analytics), not required.
APP_URL = os.environ.get("APP_URL", "http://localhost:5000")
APP_NAME = os.environ.get("APP_NAME", "Local OpenRouter Chat")

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "openai/gpt-4o-mini")

# Caps how much extracted file text gets folded into a message, to keep
# attachments from blowing out a model's context window.
MAX_ATTACHMENT_CHARS = 30_000

app = Flask(__name__)
# Covers both a multipart file upload to /api/extract and a base64 image
# embedded in an /api/chat JSON body (base64 inflates size by ~4/3).
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024


def openrouter_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_URL,
        "X-Title": APP_NAME,
    }


_SECRET_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{6,}")


def sanitize_upstream_error(status_code: int, raw_text: str) -> str:
    """Never let a raw upstream error (which can embed the API key) reach the client."""
    if status_code == 402:
        app.logger.error("OpenRouter 402 (insufficient credits): %s", raw_text)
        return json.dumps(
            {
                "error": {
                    "message": (
                        "This model needs more credits than are currently available. "
                        "Try a free model, or add credits to the OpenRouter account."
                    )
                }
            }
        )
    redacted = _SECRET_KEY_RE.sub("[redacted]", raw_text)
    if redacted != raw_text:
        app.logger.error("Redacted a key-like value from an upstream error: %s", raw_text)
    return redacted


@app.route("/")
def index() -> str:
    return render_template("index.html", default_model=DEFAULT_MODEL)


def _is_free(pricing: dict[str, Any]) -> bool:
    try:
        return float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0
    except (TypeError, ValueError):
        return False


@app.route("/api/models")
def list_models() -> ResponseReturnValue:
    """Proxy OpenRouter's model catalog so the frontend can populate the picker."""
    if not OPENROUTER_API_KEY:
        return jsonify({"error": "OPENROUTER_API_KEY is not set on the server."}), 500

    resp = requests.get(f"{OPENROUTER_BASE_URL}/models", headers=openrouter_headers(), timeout=15)
    if resp.status_code != 200:
        return jsonify({"error": "Failed to fetch models from OpenRouter", "detail": resp.text}), resp.status_code

    data: list[dict[str, Any]] = resp.json().get("data", [])
    models: list[dict[str, Any]] = [
        {
            "id": m.get("id"),
            "name": m.get("name", m.get("id")),
            "context_length": m.get("context_length"),
            "is_free": _is_free(m.get("pricing") or {}),
        }
        for m in data
    ]
    models.sort(key=lambda m: m["name"].lower())
    return jsonify(models)


ATTACHMENT_MARKER_RE = re.compile(r"\n\n<!--attachment:(.+?)-->")


def make_title(text: str, has_image: bool = False) -> str:
    marker = ATTACHMENT_MARKER_RE.search(text)
    head = " ".join((text[: marker.start()] if marker else text).split())
    if not head:
        if marker:
            head = f"📎 {marker.group(1)}"
        elif has_image:
            head = "📷 Image"
        else:
            head = "New chat"
    return head[:50] + ("…" if len(head) > 50 else "")


def _parse_message_for_export(raw: str) -> tuple[str, str | None, str | None]:
    """Splits a stored message into (display_text, image_data_url, attachment_filename)."""
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("image"):
            text = parsed.get("text")
            return (text if isinstance(text, str) else ""), parsed["image"], None

    marker = ATTACHMENT_MARKER_RE.search(raw)
    if marker:
        return raw[: marker.start()], None, marker.group(1)
    return raw, None, None


def _format_export_timestamp(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y, %I:%M %p")
    except ValueError:
        return iso


def _image_flowable(data_url: str, max_width: float = 4.5 * inch) -> Flowable | None:
    try:
        _, b64data = data_url.split(",", 1)
        img_bytes = base64.b64decode(b64data)
        iw, ih = ImageReader(io.BytesIO(img_bytes)).getSize()
        scale = min(1.0, max_width / iw) if iw else 1.0
        return RLImage(io.BytesIO(img_bytes), width=iw * scale, height=ih * scale)
    except Exception:
        return None


@app.route("/api/extract", methods=["POST"])
def extract_file() -> ResponseReturnValue:
    """Reads an uploaded text file or PDF and returns its text so it can be folded into a message."""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400

    filename = file.filename or "file"
    raw = file.read()

    text: str
    if filename.lower().endswith(".pdf") or file.mimetype == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(raw))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            return jsonify({"error": f"Could not read PDF: {exc}"}), 400
        if not text.strip():
            return jsonify({"error": "No extractable text found in this PDF (it may be a scanned image)."}), 400
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"error": "Unsupported file — please attach a text file, PDF, or image."}), 400

    if len(text) > MAX_ATTACHMENT_CHARS:
        text = text[:MAX_ATTACHMENT_CHARS] + "\n\n[...truncated...]"

    return jsonify({"filename": filename, "text": text})


@app.route("/api/chats")
def chats_list() -> ResponseReturnValue:
    return jsonify(db.list_chats())


@app.route("/api/chats/<chat_id>")
def chats_get(chat_id: str) -> ResponseReturnValue:
    chat = db.get_chat(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    return jsonify(chat)


@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def chats_delete(chat_id: str) -> ResponseReturnValue:
    db.delete_chat(chat_id)
    return jsonify({"ok": True})


@app.route("/api/chats/<chat_id>/pin", methods=["POST"])
def chats_pin(chat_id: str) -> ResponseReturnValue:
    if not db.chat_exists(chat_id):
        return jsonify({"error": "Chat not found"}), 404
    body: dict[str, Any] = request.get_json(silent=True) or {}
    pinned = bool(body.get("pinned", True))
    db.set_pinned(chat_id, pinned)
    return jsonify({"ok": True, "pinned": pinned})


@app.route("/api/chats/<chat_id>/export")
def chats_export_pdf(chat_id: str) -> ResponseReturnValue:
    chat = db.get_chat(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("export-title", parent=styles["Title"], fontName=FONT_BOLD)
    meta_style = ParagraphStyle(
        "meta", parent=styles["Normal"], fontName=FONT_REGULAR, textColor=colors.HexColor("#666666"), spaceAfter=16
    )
    role_style = ParagraphStyle("role", parent=styles["Normal"], fontName=FONT_BOLD, spaceBefore=16, spaceAfter=4)
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontName=FONT_REGULAR, spaceAfter=6, leading=15)
    attachment_style = ParagraphStyle("attachment", parent=body_style, textColor=colors.HexColor("#666666"))

    story: list[Flowable] = [
        Paragraph(xml_escape(chat["title"]), title_style),
        Paragraph(f"Model: {xml_escape(chat['model'] or '—')}", meta_style),
    ]

    for m in chat["messages"]:
        role_label = "You" if m["role"] == "user" else "Assistant"
        timestamp = _format_export_timestamp(m["created_at"])
        story.append(Paragraph(f"{role_label} — {xml_escape(timestamp)}", role_style))

        text, image_url, attachment_name = _parse_message_for_export(m["content"])
        if text.strip():
            if m["role"] == "assistant":
                story.extend(markdown_flowables(text))
            else:
                story.append(Paragraph(xml_escape(text).replace("\n", "<br/>"), body_style))
        if attachment_name:
            story.append(Paragraph(f"📎 {xml_escape(attachment_name)}", attachment_style))
        if image_url:
            image = _image_flowable(image_url)
            if image:
                story.append(image)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    doc.build(story)

    # ASCII flag matters here: \w is Unicode-aware by default, so a title made
    # entirely of non-Latin characters (e.g. Greek) would pass through unchanged
    # and later crash werkzeug's header writer, which encodes headers as latin-1.
    filename = re.sub(r"[^\w\-]+", "_", chat["title"], flags=re.ASCII).strip("_") or "chat"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


@app.route("/api/chat", methods=["POST"])
def chat() -> ResponseReturnValue:
    """Persists the user's message, streams the reply from OpenRouter as SSE, then persists it too."""
    if not OPENROUTER_API_KEY:
        return jsonify({"error": "OPENROUTER_API_KEY is not set on the server."}), 500

    body: dict[str, Any] = request.get_json(force=True) or {}
    user_message = body.get("message") or ""
    image = body.get("image")
    model = body.get("model") or DEFAULT_MODEL
    chat_id_raw = body.get("chat_id")

    if not isinstance(user_message, str):
        return jsonify({"error": "message must be a string"}), 400
    if image is not None and (not isinstance(image, str) or not image.startswith("data:image/")):
        return jsonify({"error": "image must be a data: URL"}), 400
    if not user_message.strip() and not image:
        return jsonify({"error": "message must be non-empty, or include an image"}), 400

    is_new_chat = not isinstance(chat_id_raw, str) or not chat_id_raw or not db.chat_exists(chat_id_raw)
    chat_id: str
    if is_new_chat:
        chat_id = db.create_chat(title=make_title(user_message, has_image=bool(image)), model=model)
    else:
        assert isinstance(chat_id_raw, str)
        chat_id = chat_id_raw

    # Image messages are stored as JSON ({"text", "image"}) so a follow-up
    # turn can still send the image back to the model for context; plain
    # messages (including text/PDF attachments already folded into the text
    # by the frontend) stay as plain strings.
    stored_content = json.dumps({"text": user_message, "image": image}) if image else user_message

    history = db.get_history(chat_id)
    user_message_id = db.add_message(chat_id, "user", stored_content)

    def to_openrouter_content(raw: str) -> str | list[dict[str, Any]]:
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("image"):
                parts: list[dict[str, Any]] = []
                if parsed.get("text"):
                    parts.append({"type": "text", "text": parsed["text"]})
                parts.append({"type": "image_url", "image_url": {"url": parsed["image"]}})
                return parts
        return raw

    messages = [{"role": m["role"], "content": to_openrouter_content(m["content"])} for m in history]
    messages.append({"role": "user", "content": to_openrouter_content(stored_content)})

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    def rollback_payload(error_text: str) -> dict[str, Any]:
        # The exchange never produced a reply — don't let the rejected user
        # message (e.g. an image a non-vision model refused) stick around and
        # poison every later turn's replayed history. If that was the chat's
        # only message, drop the whole (now-empty) chat too.
        db.delete_message(user_message_id)
        result: dict[str, Any] = {"error": error_text, "rolled_back": True}
        if is_new_chat and db.message_count(chat_id) == 0:
            db.delete_chat(chat_id)
            result["chat_deleted"] = True
        return result

    def generate() -> Iterator[str]:
        # Sent first so the frontend can learn the chat_id for a brand-new chat.
        yield f"data: {json.dumps({'chat_id': chat_id, 'is_new_chat': is_new_chat})}\n\n"

        assistant_text = ""
        try:
            with requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=openrouter_headers(),
                json=payload,
                stream=True,
                timeout=120,
            ) as upstream:
                if upstream.status_code != 200:
                    safe_error = sanitize_upstream_error(upstream.status_code, upstream.text)
                    yield f"data: {json.dumps(rollback_payload(safe_error))}\n\n"
                    return

                # OpenRouter sends UTF-8 without a charset param on the SSE stream;
                # without this, `requests` falls back to Latin-1 per the HTTP spec
                # default and multi-byte characters (accents, Greek, CJK, etc.) get
                # decoded as mojibake.
                upstream.encoding = "utf-8"
                for line in upstream.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str.strip() == "[DONE]":
                        continue
                    try:
                        parsed = json.loads(data_str)
                        delta = parsed.get("choices", [{}])[0].get("delta", {}).get("content")
                        if delta:
                            assistant_text += delta
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass
                    yield f"{line}\n\n"
        except requests.RequestException as exc:
            safe_msg = _SECRET_KEY_RE.sub("[redacted]", str(exc))
            if assistant_text:
                # Streaming had already started producing real content before the
                # connection died — keep the user message, just report the error.
                yield f"data: {json.dumps({'error': safe_msg})}\n\n"
            else:
                yield f"data: {json.dumps(rollback_payload(safe_msg))}\n\n"
            return
        finally:
            if assistant_text:
                db.add_message(chat_id, "assistant", assistant_text)
                db.touch_chat(chat_id)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
