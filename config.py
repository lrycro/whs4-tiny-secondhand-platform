import os
import secrets

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # No hardcoded fallback: a fixed default committed to source control would let
    # anyone who reads the repo forge session cookies / CSRF tokens. If SECRET_KEY
    # isn't set via .env, generate a fresh random one per process instead (sessions
    # just won't survive a dev-server restart, which is an acceptable trade-off for
    # never having a real, known secret sitting in git history).
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

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
