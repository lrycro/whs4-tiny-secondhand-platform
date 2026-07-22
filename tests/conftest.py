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
    with app.app_context():
        yield _db
