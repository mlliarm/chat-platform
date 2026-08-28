import json
import os

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import db

load_dotenv()
db.init_db()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Shown in the app's own HTTP headers to OpenRouter (their leaderboard/analytics), not required.
APP_URL = os.environ.get("APP_URL", "http://localhost:5000")
APP_NAME = os.environ.get("APP_NAME", "Local OpenRouter Chat")

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "openai/gpt-4o-mini")

app = Flask(__name__)


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
        }
        for m in data
    ]
    models.sort(key=lambda m: m["name"].lower())
    return jsonify(models)


def make_title(text):
    text = " ".join(text.split())
    return text[:50] + ("…" if len(text) > 50 else "")


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
    user_message = body.get("message")
    model = body.get("model") or DEFAULT_MODEL
    chat_id = body.get("chat_id")

    if not user_message or not isinstance(user_message, str):
        return jsonify({"error": "message must be a non-empty string"}), 400

    is_new_chat = not chat_id or not db.chat_exists(chat_id)
    if is_new_chat:
        chat_id = db.create_chat(title=make_title(user_message), model=model)

    history = db.get_history(chat_id)
    db.add_message(chat_id, "user", user_message)

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

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
                    yield f"data: {json.dumps({'error': upstream.text})}\n\n"
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
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
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
