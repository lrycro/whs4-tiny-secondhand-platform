import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SPEC.md 2.4: HttpOnly + SameSite=Lax always; Secure requires HTTPS
    # (ngrok demo has TLS -> set SESSION_COOKIE_SECURE=true; plain http://localhost dev -> leave false)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

    WTF_CSRF_ENABLED = True

    # product photo uploads: extension allowlist enforced in blueprints/products/forms.py,
    # size cap enforced here (also blocks oversized-upload DoS at the WSGI layer)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    PRODUCT_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "products")
