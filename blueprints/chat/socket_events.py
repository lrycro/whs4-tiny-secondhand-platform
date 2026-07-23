import time
from collections import defaultdict, deque

from flask_login import current_user
from flask_socketio import emit
from flask_socketio import join_room as sio_join_room

from extensions import db, socketio
from models import Message, User

GLOBAL_ROOM = "global"
MAX_MESSAGE_LENGTH = 1000

RATE_LIMIT_WINDOW_SECONDS = 10
RATE_LIMIT_MAX_MESSAGES = 5

# in-memory only -- fine for this single-process dev/demo app (SPEC.md's WSL+ngrok
# setup), not a multi-worker-safe rate limiter
_recent_message_times = defaultdict(deque)


def dm_room_name(user_id_a, user_id_b):
    lo, hi = sorted((user_id_a, user_id_b))
    return f"dm_{lo}_{hi}"


def _is_rate_limited(user_id):
    now = time.monotonic()
    recent = _recent_message_times[user_id]
    while recent and now - recent[0] > RATE_LIMIT_WINDOW_SECONDS:
        recent.popleft()
    if len(recent) >= RATE_LIMIT_MAX_MESSAGES:
        return True
    recent.append(now)
    return False


def _resolve_room(target_user_id):
    """Server-derived room name -- never trust a client-supplied room string directly.
    Returns None if the request is invalid/disallowed (caller should silently drop it)."""
    if target_user_id is None:
        return GLOBAL_ROOM

    try:
        target_user_id = int(target_user_id)
    except (TypeError, ValueError):
        return None

    if target_user_id == current_user.id:
        return None

    if db.session.get(User, target_user_id) is None:
        return None

    return dm_room_name(current_user.id, target_user_id)


@socketio.on("connect")
def handle_connect():
    if not current_user.is_authenticated:
        return False  # reject the connection


@socketio.on("join_room")
def handle_join_room(data=None):
    if not current_user.is_authenticated:
        return

    data = data or {}
    room = _resolve_room(data.get("target_user_id"))
    if room is None:
        return

    sio_join_room(room)


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

    room = _resolve_room(data.get("target_user_id"))
    if room is None:
        return

    if _is_rate_limited(current_user.id):
        emit("chat_error", {"message": "메시지를 너무 빠르게 보내고 있습니다. 잠시 후 다시 시도해주세요."})
        return

    message = Message(sender_id=current_user.id, room=room, content=content)
    db.session.add(message)
    db.session.commit()

    emit(
        "receive_message",
        {
            "sender_id": current_user.id,
            "sender_username": current_user.username,
            "content": content,
            "room": room,
            "created_at": message.created_at.isoformat(),
        },
        room=room,
    )
