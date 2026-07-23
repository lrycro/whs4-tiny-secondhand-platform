import io
import re

from PIL import Image

VALID_PASSWORD = "Passw0rd!"


def valid_photo():
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(buf, format="PNG")
    buf.seek(0)
    return (buf, "photo.png")


def extract_csrf(html):
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "csrf token not found on page"
    return match.group(1)


def register(client, username="tester1", password=VALID_PASSWORD, confirm=None):
    resp = client.get("/register")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/register",
        data={
            "username": username,
            "password": password,
            "password_confirm": confirm if confirm is not None else password,
            "csrf_token": token,
        },
        follow_redirects=True,
    )


def login(client, username="tester1", password=VALID_PASSWORD, extra_qs=""):
    resp = client.get("/login" + extra_qs)
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/login" + extra_qs,
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=False,
    )
