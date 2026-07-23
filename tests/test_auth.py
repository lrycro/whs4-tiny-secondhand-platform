from datetime import timedelta

from models import LOGIN_LOCK_THRESHOLD, User, UserStatus, _utcnow
from tests.helpers import VALID_PASSWORD
from tests.helpers import extract_csrf as _extract_csrf
from tests.helpers import login as _login
from tests.helpers import register as _register


def test_register_success_hashes_password(client, db):
    resp = _register(client)
    assert resp.status_code == 200
    assert "로그인해주세요" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="tester1").first()
    assert user is not None
    assert user.password_hash != VALID_PASSWORD
    assert user.check_password(VALID_PASSWORD)
    assert user.status == UserStatus.ACTIVE


def test_register_duplicate_username_rejected(client, db):
    _register(client, username="dupuser")
    resp = _register(client, username="dupuser")
    assert "이미 사용 중인 아이디입니다" in resp.get_data(as_text=True)
    assert User.query.filter_by(username="dupuser").count() == 1


def test_register_weak_password_rejected(client, db):
    resp = _register(client, username="weakpw", password="abcdefgh", confirm="abcdefgh")
    assert "영문, 숫자, 특수문자를 포함" in resp.get_data(as_text=True)
    assert User.query.filter_by(username="weakpw").first() is None


def test_register_password_mismatch_rejected(client, db):
    resp = _register(client, username="mismatch", password=VALID_PASSWORD, confirm="Different1!")
    assert "비밀번호가 일치하지 않습니다" in resp.get_data(as_text=True)
    assert User.query.filter_by(username="mismatch").first() is None


def test_login_success(client, db):
    _register(client, username="loginok")
    resp = _login(client, username="loginok")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"

    index_resp = client.get("/", follow_redirects=True)
    assert "loginok님 환영합니다" in index_resp.get_data(as_text=True)


def test_login_wrong_password_shows_generic_error(client, db):
    _register(client, username="wrongpw")
    resp = _login(client, username="wrongpw", password="WrongPass1!")
    assert resp.status_code == 200
    assert "아이디 또는 비밀번호가 올바르지 않습니다" in resp.get_data(as_text=True)


def test_login_nonexistent_user_shows_same_generic_error(client, db):
    resp = _login(client, username="ghost", password=VALID_PASSWORD)
    assert resp.status_code == 200
    assert "아이디 또는 비밀번호가 올바르지 않습니다" in resp.get_data(as_text=True)


def test_login_suspended_user_blocked(client, db, app):
    _register(client, username="suspended1")
    with app.app_context():
        user = User.query.filter_by(username="suspended1").first()
        user.status = UserStatus.SUSPENDED
        db.session.commit()

    resp = _login(client, username="suspended1")
    assert resp.status_code == 200
    assert "휴면 처리된 계정입니다" in resp.get_data(as_text=True)


def test_logout_requires_login(client, db):
    # fetch a valid CSRF token from any page so this exercises the login_required
    # check specifically, not CSRF rejection
    token = _extract_csrf(client.get("/login").get_data(as_text=True))
    resp = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_logout_clears_session(client, db):
    _register(client, username="logoutuser")
    _login(client, username="logoutuser")

    token = _extract_csrf(client.get("/").get_data(as_text=True))
    logout_resp = client.post("/logout", data={"csrf_token": token}, follow_redirects=True)
    assert "로그아웃 되었습니다" in logout_resp.get_data(as_text=True)

    # session cleared -> logout again is unauthenticated -> redirected to login
    token2 = _extract_csrf(client.get("/login").get_data(as_text=True))
    resp = client.post("/logout", data={"csrf_token": token2}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_csrf_protection_blocks_missing_token(client, db):
    resp = client.post(
        "/register",
        data={"username": "nocsrf", "password": VALID_PASSWORD, "password_confirm": VALID_PASSWORD},
    )
    assert resp.status_code == 400
    assert User.query.filter_by(username="nocsrf").first() is None


def test_login_open_redirect_is_blocked(client, db):
    _register(client, username="redirtest")
    resp = _login(client, username="redirtest", extra_qs="?next=http://evil.example.com/steal")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_login_protocol_relative_redirect_is_blocked(client, db):
    _register(client, username="redirtest2")
    resp = _login(client, username="redirtest2", extra_qs="?next=//evil.example.com/steal")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_login_marks_session_permanent(client, db):
    _register(client, username="permtest")
    _login(client, username="permtest")
    with client.session_transaction() as sess:
        assert sess.permanent is True


def test_failed_login_increments_counter(client, db):
    _register(client, username="failcount")
    _login(client, username="failcount", password="WrongPass1!")

    user = User.query.filter_by(username="failcount").first()
    assert user.failed_login_attempts == 1
    assert user.is_locked() is False


def test_successful_login_resets_failed_counter(client, db):
    _register(client, username="resetcount")
    _login(client, username="resetcount", password="WrongPass1!")
    _login(client, username="resetcount", password=VALID_PASSWORD)

    user = User.query.filter_by(username="resetcount").first()
    assert user.failed_login_attempts == 0


def test_account_locks_after_threshold_failures(client, db):
    _register(client, username="lockme")

    for _ in range(LOGIN_LOCK_THRESHOLD):
        _login(client, username="lockme", password="WrongPass1!")

    user = User.query.filter_by(username="lockme").first()
    assert user.is_locked() is True
    assert user.failed_login_attempts == 0  # reset when the lock is applied

    # even the CORRECT password is rejected while locked, with the same generic message
    resp = _login(client, username="lockme", password=VALID_PASSWORD)
    assert resp.status_code == 200
    assert "아이디 또는 비밀번호가 올바르지 않습니다" in resp.get_data(as_text=True)


def test_lock_expires_and_correct_password_then_succeeds(client, db, app):
    _register(client, username="lockexpire")
    for _ in range(LOGIN_LOCK_THRESHOLD):
        _login(client, username="lockexpire", password="WrongPass1!")

    with app.app_context():
        user = User.query.filter_by(username="lockexpire").first()
        assert user.is_locked() is True
        user.locked_until = _utcnow() - timedelta(seconds=1)  # simulate the lock expiring
        db.session.commit()

    resp = _login(client, username="lockexpire", password=VALID_PASSWORD)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
