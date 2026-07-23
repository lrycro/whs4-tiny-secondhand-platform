from extensions import db
from models import AdminActionLog, Product, ProductStatus, Report, ReportTargetType, User, UserRole, UserStatus
from tests.helpers import extract_csrf, login, register, valid_photo


def _make_admin(app, username):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        user.role = UserRole.ADMIN
        db.session.commit()


def _logout(client):
    token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": token}, follow_redirects=True)


def _create_product(client, name="관리자테스트상품", seller_username=None):
    resp = client.get("/products/new")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/products/new",
        data={"name": name, "description": "설명", "price": "1000", "csrf_token": token, "photo": valid_photo()},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_admin_dashboard_requires_login(client, db):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_dashboard_requires_admin_role(client, db):
    register(client, username="regularuser")
    login(client, username="regularuser")

    for path in ["/admin/", "/admin/users", "/admin/products", "/admin/reports"]:
        resp = client.get(path)
        assert resp.status_code == 403, path


def test_admin_dashboard_accessible_to_admin(client, db, app):
    register(client, username="adminuser1")
    _make_admin(app, "adminuser1")
    login(client, username="adminuser1")

    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "관리자 대시보드" in resp.get_data(as_text=True)


def test_admin_users_list_shows_all_users(client, db, app):
    register(client, username="plainuser1")
    register(client, username="adminuser2")
    _make_admin(app, "adminuser2")
    login(client, username="adminuser2")

    resp = client.get("/admin/users")
    html = resp.get_data(as_text=True)
    assert "plainuser1" in html
    assert "adminuser2" in html


def test_toggle_user_status_suspends_and_unsuspends(client, db, app):
    register(client, username="togglee1")
    register(client, username="adminuser3")
    _make_admin(app, "adminuser3")
    login(client, username="adminuser3")

    with app.app_context():
        target_id = User.query.filter_by(username="togglee1").first().id

    token = extract_csrf(client.get("/admin/users").get_data(as_text=True))
    resp = client.post(
        f"/admin/users/{target_id}/toggle-status", data={"csrf_token": token}, follow_redirects=True
    )
    assert "휴면 처리했습니다" in resp.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(id=target_id).first().status == UserStatus.SUSPENDED

    token2 = extract_csrf(client.get("/admin/users").get_data(as_text=True))
    resp2 = client.post(
        f"/admin/users/{target_id}/toggle-status", data={"csrf_token": token2}, follow_redirects=True
    )
    assert "휴면을 해제했습니다" in resp2.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(id=target_id).first().status == UserStatus.ACTIVE


def test_toggle_user_status_resets_report_count(client, db, app):
    register(client, username="togglee2")
    register(client, username="adminuser4")
    _make_admin(app, "adminuser4")

    with app.app_context():
        target = User.query.filter_by(username="togglee2").first()
        target.status = UserStatus.SUSPENDED
        target.report_count = 5
        db.session.commit()
        target_id = target.id

    login(client, username="adminuser4")
    token = extract_csrf(client.get("/admin/users").get_data(as_text=True))
    client.post(f"/admin/users/{target_id}/toggle-status", data={"csrf_token": token}, follow_redirects=True)

    with app.app_context():
        target = User.query.filter_by(id=target_id).first()
        assert target.status == UserStatus.ACTIVE
        assert target.report_count == 0


def test_admin_cannot_toggle_own_status(client, db, app):
    register(client, username="adminuser5")
    _make_admin(app, "adminuser5")
    login(client, username="adminuser5")

    with app.app_context():
        my_id = User.query.filter_by(username="adminuser5").first().id

    token = extract_csrf(client.get("/admin/users").get_data(as_text=True))
    resp = client.post(f"/admin/users/{my_id}/toggle-status", data={"csrf_token": token}, follow_redirects=True)
    assert "본인의 상태는 변경할 수 없습니다" in resp.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(id=my_id).first().status == UserStatus.ACTIVE


def test_non_admin_cannot_post_toggle_user_status(client, db, app):
    register(client, username="victim1")
    register(client, username="attacker1")
    login(client, username="attacker1")

    with app.app_context():
        victim_id = User.query.filter_by(username="victim1").first().id

    token = extract_csrf(client.get("/").get_data(as_text=True))
    resp = client.post(f"/admin/users/{victim_id}/toggle-status", data={"csrf_token": token})
    assert resp.status_code == 403
    with app.app_context():
        assert User.query.filter_by(id=victim_id).first().status == UserStatus.ACTIVE


def test_toggle_product_status_blocks_and_unblocks(client, db, app):
    register(client, username="seller1")
    login(client, username="seller1")
    _create_product(client, name="관리대상상품")
    _logout(client)

    register(client, username="adminuser6")
    _make_admin(app, "adminuser6")
    login(client, username="adminuser6")

    with app.app_context():
        product_id = Product.query.filter_by(name="관리대상상품").first().id

    token = extract_csrf(client.get("/admin/products").get_data(as_text=True))
    resp = client.post(
        f"/admin/products/{product_id}/toggle-status", data={"csrf_token": token}, follow_redirects=True
    )
    assert "상품을 차단했습니다" in resp.get_data(as_text=True)
    with app.app_context():
        assert Product.query.filter_by(id=product_id).first().status == ProductStatus.BLOCKED

    token2 = extract_csrf(client.get("/admin/products").get_data(as_text=True))
    resp2 = client.post(
        f"/admin/products/{product_id}/toggle-status", data={"csrf_token": token2}, follow_redirects=True
    )
    assert "차단을 해제했습니다" in resp2.get_data(as_text=True)
    with app.app_context():
        assert Product.query.filter_by(id=product_id).first().status == ProductStatus.ACTIVE


def test_admin_delete_product_removes_it(client, db, app):
    register(client, username="seller2")
    login(client, username="seller2")
    _create_product(client, name="삭제될관리상품")
    _logout(client)

    register(client, username="adminuser7")
    _make_admin(app, "adminuser7")
    login(client, username="adminuser7")

    with app.app_context():
        product_id = Product.query.filter_by(name="삭제될관리상품").first().id

    token = extract_csrf(client.get("/admin/products").get_data(as_text=True))
    resp = client.post(f"/admin/products/{product_id}/delete", data={"csrf_token": token}, follow_redirects=True)
    assert "강제 삭제했습니다" in resp.get_data(as_text=True)
    with app.app_context():
        assert Product.query.filter_by(id=product_id).first() is None


def test_admin_actions_are_logged(client, db, app):
    register(client, username="seller3")
    login(client, username="seller3")
    _create_product(client, name="로그테스트상품")
    _logout(client)

    register(client, username="adminuser8")
    _make_admin(app, "adminuser8")
    login(client, username="adminuser8")

    with app.app_context():
        product_id = Product.query.filter_by(name="로그테스트상품").first().id
        admin_id = User.query.filter_by(username="adminuser8").first().id

    token = extract_csrf(client.get("/admin/products").get_data(as_text=True))
    client.post(f"/admin/products/{product_id}/toggle-status", data={"csrf_token": token}, follow_redirects=True)

    with app.app_context():
        log = AdminActionLog.query.filter_by(target_type="product", target_id=product_id).first()
        assert log is not None
        assert log.action == "product_block"
        assert log.admin_id == admin_id


def test_admin_reports_list_shows_reports(client, db, app):
    register(client, username="reporter1")
    register(client, username="reportedtarget")
    login(client, username="reporter1")

    with app.app_context():
        target_id = User.query.filter_by(username="reportedtarget").first().id
        db.session.add(
            Report(
                reporter_id=User.query.filter_by(username="reporter1").first().id,
                target_type=ReportTargetType.USER,
                target_id=target_id,
                reason="테스트 신고 사유",
            )
        )
        db.session.commit()
    _logout(client)

    register(client, username="adminuser9")
    _make_admin(app, "adminuser9")
    login(client, username="adminuser9")

    resp = client.get("/admin/reports")
    html = resp.get_data(as_text=True)
    assert "테스트 신고 사유" in html
    assert "reportedtarget" in html
    assert "reporter1" in html
