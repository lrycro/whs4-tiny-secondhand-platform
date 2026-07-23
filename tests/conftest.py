import os
import tempfile

import pytest

from app import create_app
from config import Config
from extensions import db as _db


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        WTF_CSRF_ENABLED = True
        SESSION_COOKIE_SECURE = False  # test client talks plain http, like local dev

    flask_app = create_app(TestConfig)

    yield flask_app

    with flask_app.app_context():
        _db.session.remove()
        _db.drop_all()
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    # NOT wrapped in `with app.app_context()`: Flask reuses an already-active app
    # context for nested test-client/Socket.IO requests instead of pushing a fresh
    # one, which means Flask-Login's g._login_user and Flask-WTF's g.csrf_token
    # leak between different test_client() instances/sessions sharing one ambient
    # context (confirmed: a second client's CSRF token would validate against the
    # first client's session -> "CSRF session token missing"). Direct model
    # queries in test bodies must open their own `with app.app_context():` block.
    yield _db


@pytest.fixture(autouse=True)
def _reset_chat_rate_limiter():
    # module-level in-memory state in blueprints/chat/socket_events.py, keyed by
    # user_id -- since every test's sqlite DB restarts ids from 1, an unrelated
    # earlier test's "user 1" can leave stale rate-limit entries for this test's
    # own "user 1"
    from blueprints.chat.socket_events import _recent_message_times

    _recent_message_times.clear()
    yield
    _recent_message_times.clear()
