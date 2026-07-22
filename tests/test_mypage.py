from models import User
from tests.helpers import VALID_PASSWORD, extract_csrf, login, register


def test_mypage_requires_login(client, db):
    resp = client.get("/mypage", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_update_bio_success(client, db):
    register(client, username="bioupdate")
    login(client, username="bioupdate")

    token = extract_csrf(client.get("/mypage").get_data(as_text=True))
    resp = client.post(
        "/mypage",
        data={"bio": "안녕하세요, 반갑습니다.", "submit_bio": "소개글 저장", "csrf_token": token},
        follow_redirects=True,
    )
    assert "소개글이 수정되었습니다" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="bioupdate").first()
    assert user.bio == "안녕하세요, 반갑습니다."


def test_update_bio_too_long_rejected(client, db):
    register(client, username="biolong")
    login(client, username="biolong")

    token = extract_csrf(client.get("/mypage").get_data(as_text=True))
    resp = client.post(
        "/mypage",
        data={"bio": "x" * 501, "submit_bio": "소개글 저장", "csrf_token": token},
        follow_redirects=True,
    )
    assert "500자 이하로 입력해주세요" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="biolong").first()
    assert user.bio is None


def test_change_password_success(client, db):
    register(client, username="pwchange")
    login(client, username="pwchange")

    token = extract_csrf(client.get("/mypage").get_data(as_text=True))
    resp = client.post(
        "/mypage",
        data={
            "current_password": VALID_PASSWORD,
            "new_password": "NewPassw0rd!",
            "new_password_confirm": "NewPassw0rd!",
            "submit_password": "비밀번호 변경",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "비밀번호가 변경되었습니다" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="pwchange").first()
    assert user.check_password("NewPassw0rd!")
    assert not user.check_password(VALID_PASSWORD)

    # log out, then confirm old password no longer authenticates and the new one does
    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    fail_resp = login(client, username="pwchange", password=VALID_PASSWORD)
    assert fail_resp.status_code == 200
    assert "아이디 또는 비밀번호가 올바르지 않습니다" in fail_resp.get_data(as_text=True)

    ok_resp = login(client, username="pwchange", password="NewPassw0rd!")
    assert ok_resp.status_code == 302
    assert ok_resp.headers["Location"] == "/"


def test_change_password_wrong_current_rejected(client, db):
    register(client, username="pwwrong")
    login(client, username="pwwrong")

    token = extract_csrf(client.get("/mypage").get_data(as_text=True))
    resp = client.post(
        "/mypage",
        data={
            "current_password": "WrongCurrent1!",
            "new_password": "NewPassw0rd!",
            "new_password_confirm": "NewPassw0rd!",
            "submit_password": "비밀번호 변경",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "현재 비밀번호가 일치하지 않습니다" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="pwwrong").first()
    assert user.check_password(VALID_PASSWORD)


def test_change_password_weak_new_password_rejected(client, db):
    register(client, username="pwweak")
    login(client, username="pwweak")

    token = extract_csrf(client.get("/mypage").get_data(as_text=True))
    resp = client.post(
        "/mypage",
        data={
            "current_password": VALID_PASSWORD,
            "new_password": "weakpassword",
            "new_password_confirm": "weakpassword",
            "submit_password": "비밀번호 변경",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "영문, 숫자, 특수문자를 포함" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="pwweak").first()
    assert user.check_password(VALID_PASSWORD)


def test_change_password_mismatch_rejected(client, db):
    register(client, username="pwmismatch")
    login(client, username="pwmismatch")

    token = extract_csrf(client.get("/mypage").get_data(as_text=True))
    resp = client.post(
        "/mypage",
        data={
            "current_password": VALID_PASSWORD,
            "new_password": "NewPassw0rd!",
            "new_password_confirm": "Different1!",
            "submit_password": "비밀번호 변경",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "새 비밀번호가 일치하지 않습니다" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="pwmismatch").first()
    assert user.check_password(VALID_PASSWORD)


def test_mypage_only_affects_current_user(client, db, app):
    register(client, username="userA")
    register(client, username="userB")

    login(client, username="userA")
    token = extract_csrf(client.get("/mypage").get_data(as_text=True))
    client.post(
        "/mypage",
        data={"bio": "A의 소개글", "submit_bio": "소개글 저장", "csrf_token": token},
        follow_redirects=True,
    )

    with app.app_context():
        user_a = User.query.filter_by(username="userA").first()
        user_b = User.query.filter_by(username="userB").first()
        assert user_a.bio == "A의 소개글"
        assert user_b.bio is None
