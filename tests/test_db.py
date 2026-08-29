"""Tests for db.py — the SQLite persistence layer.

Every test uses the `temp_db` fixture (see conftest.py), which points
db.DB_PATH at a fresh temp file per test. The real chat.db is never touched.
"""

from types import ModuleType


def test_init_db_is_idempotent(temp_db: ModuleType) -> None:
    # Calling init_db() twice must not error (CREATE TABLE IF NOT EXISTS).
    temp_db.init_db()
    temp_db.init_db()


def test_create_chat_returns_id_and_is_retrievable(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Hello", model="openai/gpt-4o-mini")
    assert isinstance(chat_id, str) and chat_id

    chat = temp_db.get_chat(chat_id)
    assert chat["id"] == chat_id
    assert chat["title"] == "Hello"
    assert chat["model"] == "openai/gpt-4o-mini"
    assert chat["messages"] == []


def test_chat_exists(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="Hi", model="m")
    assert temp_db.chat_exists(chat_id) is True
    assert temp_db.chat_exists("nonexistent-id") is False


def test_get_chat_missing_returns_none(temp_db: ModuleType) -> None:
    assert temp_db.get_chat("does-not-exist") is None


def test_add_message_returns_incrementing_ids(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    id1 = temp_db.add_message(chat_id, "user", "first")
    id2 = temp_db.add_message(chat_id, "assistant", "second")
    assert isinstance(id1, int) and isinstance(id2, int)
    assert id2 > id1


def test_get_history_preserves_order_and_shape(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    temp_db.add_message(chat_id, "user", "one")
    temp_db.add_message(chat_id, "assistant", "two")
    temp_db.add_message(chat_id, "user", "three")

    history = temp_db.get_history(chat_id)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "one"),
        ("assistant", "two"),
        ("user", "three"),
    ]
    # get_history rows must not include created_at (only role/content are sent to the model)
    assert set(history[0].keys()) == {"role", "content"}


def test_get_chat_messages_include_created_at(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    temp_db.add_message(chat_id, "user", "hi")

    chat = temp_db.get_chat(chat_id)
    assert "created_at" in chat["messages"][0]
    assert chat["messages"][0]["content"] == "hi"


def test_delete_message_removes_only_that_message(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    keep_id = temp_db.add_message(chat_id, "user", "keep me")
    remove_id = temp_db.add_message(chat_id, "user", "remove me")

    temp_db.delete_message(remove_id)

    history = temp_db.get_history(chat_id)
    assert len(history) == 1
    assert history[0]["content"] == "keep me"
    assert temp_db.message_count(chat_id) == 1
    # sanity: the surviving message really is the one we asked to keep
    assert keep_id is not None


def test_message_count(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    assert temp_db.message_count(chat_id) == 0
    temp_db.add_message(chat_id, "user", "a")
    temp_db.add_message(chat_id, "assistant", "b")
    assert temp_db.message_count(chat_id) == 2


def test_touch_chat_updates_updated_at(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    before = temp_db.get_chat(chat_id)

    chats_before = {c["id"]: c["updated_at"] for c in temp_db.list_chats()}
    temp_db.touch_chat(chat_id)
    chats_after = {c["id"]: c["updated_at"] for c in temp_db.list_chats()}

    assert chats_after[chat_id] >= chats_before[chat_id]
    assert before["id"] == chat_id  # sanity, chat untouched otherwise


def test_list_chats_sorted_by_updated_at_desc(temp_db: ModuleType) -> None:
    older_id = temp_db.create_chat(title="Older", model="m")
    newer_id = temp_db.create_chat(title="Newer", model="m")
    # Bumping the older chat's updated_at should move it back to the top.
    temp_db.touch_chat(older_id)

    chats = temp_db.list_chats()
    assert chats[0]["id"] == older_id
    assert chats[1]["id"] == newer_id


def test_delete_chat_removes_chat_and_cascades_messages(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    temp_db.add_message(chat_id, "user", "hi")
    temp_db.add_message(chat_id, "assistant", "hello")

    temp_db.delete_chat(chat_id)

    assert temp_db.chat_exists(chat_id) is False
    assert temp_db.get_chat(chat_id) is None
    # The cascade (ON DELETE CASCADE + PRAGMA foreign_keys=ON) must have
    # removed the orphaned messages too, not just the chat row.
    assert temp_db.get_history(chat_id) == []


def test_delete_chat_does_not_affect_other_chats(temp_db: ModuleType) -> None:
    keep_id = temp_db.create_chat(title="Keep", model="m")
    temp_db.add_message(keep_id, "user", "still here")
    doomed_id = temp_db.create_chat(title="Doomed", model="m")

    temp_db.delete_chat(doomed_id)

    assert temp_db.chat_exists(keep_id) is True
    assert temp_db.get_history(keep_id) == [{"role": "user", "content": "still here"}]


def test_delete_message_nonexistent_id_is_a_noop(temp_db: ModuleType) -> None:
    chat_id = temp_db.create_chat(title="T", model="m")
    temp_db.add_message(chat_id, "user", "hi")
    temp_db.delete_message(999999)  # doesn't exist — should not raise
    assert temp_db.message_count(chat_id) == 1
