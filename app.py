import io
import json
import os
import re

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from pypdf import PdfReader

import db

load_dotenv()
db.init_db()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
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


def openrouter_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_URL,
        "X-Title": APP_NAME,
    }


@app.route("/")
def index():
    return render_template("index.html", default_model=DEFAULT_MODEL)


def _is_free(pricing):
    try:
        return float(pricing.get("prompt", 1)) == 0 and float(pricing.get("completion", 1)) == 0
    except (TypeError, ValueError):
        return False


@app.route("/api/models")
def list_models():
    """Proxy OpenRouter's model catalog so the frontend can populate the picker."""
    if not OPENROUTER_API_KEY:
        return jsonify({"error": "OPENROUTER_API_KEY is not set on the server."}), 500

    resp = requests.get(f"{OPENROUTER_BASE_URL}/models", headers=openrouter_headers(), timeout=15)
    if resp.status_code != 200:
        return jsonify({"error": "Failed to fetch models from OpenRouter", "detail": resp.text}), resp.status_code

    data = resp.json().get("data", [])
    models = [
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


def make_title(text, has_image=False):
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


@app.route("/api/extract", methods=["POST"])
def extract_file():
    """Reads an uploaded text file or PDF and returns its text so it can be folded into a message."""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400

    filename = file.filename or "file"
    raw = file.read()

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
def chats_list():
    return jsonify(db.list_chats())


@app.route("/api/chats/<chat_id>")
def chats_get(chat_id):
    chat = db.get_chat(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    return jsonify(chat)


@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def chats_delete(chat_id):
    db.delete_chat(chat_id)
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def chat():
    """Persists the user's message, streams the reply from OpenRouter as SSE, then persists it too."""
    if not OPENROUTER_API_KEY:
        return jsonify({"error": "OPENROUTER_API_KEY is not set on the server."}), 500

    body = request.get_json(force=True) or {}
    user_message = body.get("message") or ""
    image = body.get("image")
    model = body.get("model") or DEFAULT_MODEL
    chat_id = body.get("chat_id")

    if not isinstance(user_message, str):
        return jsonify({"error": "message must be a string"}), 400
    if image is not None and (not isinstance(image, str) or not image.startswith("data:image/")):
        return jsonify({"error": "image must be a data: URL"}), 400
    if not user_message.strip() and not image:
        return jsonify({"error": "message must be non-empty, or include an image"}), 400

    is_new_chat = not chat_id or not db.chat_exists(chat_id)
    if is_new_chat:
        chat_id = db.create_chat(title=make_title(user_message, has_image=bool(image)), model=model)

    # Image messages are stored as JSON ({"text", "image"}) so a follow-up
    # turn can still send the image back to the model for context; plain
    # messages (including text/PDF attachments already folded into the text
    # by the frontend) stay as plain strings.
    stored_content = json.dumps({"text": user_message, "image": image}) if image else user_message

    history = db.get_history(chat_id)
    user_message_id = db.add_message(chat_id, "user", stored_content)

    def to_openrouter_content(raw):
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("image"):
                parts = []
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

    def rollback_payload(error_text):
        # The exchange never produced a reply — don't let the rejected user
        # message (e.g. an image a non-vision model refused) stick around and
        # poison every later turn's replayed history. If that was the chat's
        # only message, drop the whole (now-empty) chat too.
        db.delete_message(user_message_id)
        result = {"error": error_text, "rolled_back": True}
        if is_new_chat and db.message_count(chat_id) == 0:
            db.delete_chat(chat_id)
            result["chat_deleted"] = True
        return result

    def generate():
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
                    yield f"data: {json.dumps(rollback_payload(upstream.text))}\n\n"
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
            if assistant_text:
                # Streaming had already started producing real content before the
                # connection died — keep the user message, just report the error.
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            else:
                yield f"data: {json.dumps(rollback_payload(str(exc)))}\n\n"
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
