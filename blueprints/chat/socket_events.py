import time
from collections import defaultdict, deque

from flask_login import current_user
from flask_socketio import emit
from flask_socketio import join_room as sio_join_room

from extensions import db, socketio
from models import ChatThread, GlobalMessage, Message, format_kst_time

GLOBAL_ROOM = "global"
MAX_MESSAGE_LENGTH = 1000

RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_MAX_MESSAGES = 5

# in-memory only -- fine for this single-process dev/demo app (SPEC.md's WSL+ngrok
# setup), not a multi-worker-safe rate limiter
_recent_message_times = defaultdict(deque)


def _is_rate_limited(user_id):
    now = time.monotonic()
    recent = _recent_message_times[user_id]
    while recent and now - recent[0] > RATE_LIMIT_WINDOW_SECONDS:
        recent.popleft()
    if len(recent) >= RATE_LIMIT_MAX_MESSAGES:
        return True
    recent.append(now)
    return False


def _resolve_thread(thread_id):
    """Server-verified chat thread -- the client only ever supplies a thread_id;
    membership (is current_user the buyer or the product's seller?) is re-checked
    against the DB on every call, never trusted from the client. Returns None if
    the request is invalid/disallowed (caller should silently drop it)."""
    try:
        thread_id = int(thread_id)
    except (TypeError, ValueError):
        return None

    thread = db.session.get(ChatThread, thread_id)
    if thread is None:
        return None

    if not thread.is_participant(current_user.id):
        return None

    return thread


@socketio.on("connect")
def handle_connect():
    if not current_user.is_authenticated:
        return False  # reject the connection


@socketio.on("join_room")
def handle_join_room(data=None):
    if not current_user.is_authenticated:
        return

    data = data or {}
    thread_id = data.get("thread_id")

    # no thread_id -> the F9 all-users global room; a thread_id -> a specific
    # product's 1:1 thread, membership re-verified against the DB every time
    if thread_id is None:
        sio_join_room(GLOBAL_ROOM)
        return

    thread = _resolve_thread(thread_id)
    if thread is None:
        return

    sio_join_room(thread.room_name())


@socketio.on("send_message")
def handle_send_message(data=None):
    if not current_user.is_authenticated:
        return

    data = data or {}
    content = (data.get("content") or "").strip()
    if not content:
        return
    if len(content) > MAX_MESSAGE_LENGTH:
        emit("chat_error", {"message": f"메시지는 {MAX_MESSAGE_LENGTH}자 이하로 입력해주세요."})
        return

    if _is_rate_limited(current_user.id):
        emit("chat_error", {"message": "메시지를 너무 빠르게 보내고 있습니다. 잠시 후 다시 시도해주세요."})
        return

    thread_id = data.get("thread_id")

    if thread_id is None:
        message = GlobalMessage(sender_id=current_user.id, content=content)
        db.session.add(message)
        db.session.commit()

        emit(
            "receive_message",
            {
                "sender_id": current_user.id,
                "sender_username": current_user.username,
                "content": content,
                "thread_id": None,
                "time": format_kst_time(message.created_at),
            },
            room=GLOBAL_ROOM,
        )
        return

    thread = _resolve_thread(thread_id)
    if thread is None:
        return

    message = Message(sender_id=current_user.id, thread_id=thread.id, content=content)
    db.session.add(message)
    db.session.commit()

    emit(
        "receive_message",
        {
            "sender_id": current_user.id,
            "sender_username": current_user.username,
            "content": content,
            "thread_id": thread.id,
            "time": format_kst_time(message.created_at),
        },
        room=thread.room_name(),
    )
