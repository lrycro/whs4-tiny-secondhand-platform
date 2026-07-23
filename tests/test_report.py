from models import Product, REPORT_BLOCK_THRESHOLD, Report, User, UserStatus, ProductStatus
from tests.helpers import extract_csrf, login, register, valid_photo


def _logout(client):
    token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": token}, follow_redirects=True)


def _create_product(client, name="신고테스트상품"):
    resp = client.get("/products/new")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/products/new",
        data={"name": name, "description": "설명", "price": "1000", "csrf_token": token, "photo": valid_photo()},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _report(client, target_type, target_id, reason="스팸/사기 의심됩니다"):
    resp = client.get(f"/report?target_type={target_type}&target_id={target_id}")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/report",
        data={"target_type": target_type, "target_id": target_id, "reason": reason, "csrf_token": token},
        follow_redirects=True,
    )


def _get_product_id(app, name):
    with app.app_context():
        return Product.query.filter_by(name=name).first().id


def _get_user_id(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().id


def test_report_requires_login(client, db):
    resp = client.get("/report?target_type=product&target_id=1", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_report_invalid_target_type_redirects(client, db):
    register(client, username="reporter1")
    login(client, username="reporter1")

    resp = client.get("/report?target_type=bogus&target_id=1", follow_redirects=True)
    assert "신고 대상이 올바르지 않습니다" in resp.get_data(as_text=True)


def test_report_missing_target_id_redirects(client, db):
    register(client, username="reporter2")
    login(client, username="reporter2")

    resp = client.get("/report?target_type=product", follow_redirects=True)
    assert "신고 대상이 올바르지 않습니다" in resp.get_data(as_text=True)


def test_report_nonexistent_product_404(client, db):
    register(client, username="reporter3")
    login(client, username="reporter3")

    resp = client.get("/report?target_type=product&target_id=999999")
    assert resp.status_code == 404


def test_report_nonexistent_user_404(client, db):
    register(client, username="reporter4")
    login(client, username="reporter4")

    resp = client.get("/report?target_type=user&target_id=999999")
    assert resp.status_code == 404


def test_report_own_product_blocked(client, db, app):
    register(client, username="ownerreport")
    login(client, username="ownerreport")
    _create_product(client, name="내상품")
    product_id = _get_product_id(app, "내상품")

    resp = client.get(f"/report?target_type=product&target_id={product_id}", follow_redirects=True)
    assert "본인의 상품은 신고할 수 없습니다" in resp.get_data(as_text=True)


def test_report_self_blocked(client, db, app):
    register(client, username="selfreport")
    login(client, username="selfreport")
    my_id = _get_user_id(app, "selfreport")

    resp = client.get(f"/report?target_type=user&target_id={my_id}", follow_redirects=True)
    assert "본인을 신고할 수 없습니다" in resp.get_data(as_text=True)


def test_report_product_success(client, db, app):
    register(client, username="sellerA")
    login(client, username="sellerA")
    _create_product(client, name="신고당할상품")
    product_id = _get_product_id(app, "신고당할상품")
    _logout(client)

    register(client, username="reporterA")
    login(client, username="reporterA")
    resp = _report(client, "product", product_id, reason="가짜 상품인 것 같습니다")
    assert "신고가 접수되었습니다" in resp.get_data(as_text=True)

    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        assert product.report_count == 1
        assert product.status == ProductStatus.ACTIVE

        report_row = Report.query.filter_by(target_type="product", target_id=product_id).first()
        assert report_row is not None
        assert report_row.reason == "가짜 상품인 것 같습니다"


def test_report_user_success(client, db, app):
    register(client, username="targetuser")  # not logged in -- registering doesn't authenticate
    target_id = _get_user_id(app, "targetuser")

    register(client, username="reporterB")
    login(client, username="reporterB")
    resp = _report(client, "user", target_id, reason="욕설을 사용합니다")
    assert "신고가 접수되었습니다" in resp.get_data(as_text=True)

    with app.app_context():
        user = User.query.filter_by(id=target_id).first()
        assert user.report_count == 1
        assert user.status == UserStatus.ACTIVE


def test_report_missing_reason_rejected(client, db, app):
    register(client, username="sellerB")
    login(client, username="sellerB")
    _create_product(client, name="사유없음상품")
    product_id = _get_product_id(app, "사유없음상품")
    _logout(client)

    register(client, username="reporterC")
    login(client, username="reporterC")
    resp = _report(client, "product", product_id, reason="")
    assert "신고 사유를 입력해주세요" in resp.get_data(as_text=True)

    with app.app_context():
        assert Report.query.count() == 0


def test_report_reason_too_long_rejected(client, db, app):
    register(client, username="sellerC")
    login(client, username="sellerC")
    _create_product(client, name="긴사유상품")
    product_id = _get_product_id(app, "긴사유상품")
    _logout(client)

    register(client, username="reporterD")
    login(client, username="reporterD")
    resp = _report(client, "product", product_id, reason="x" * 501)
    assert "500자 이하로 입력해주세요" in resp.get_data(as_text=True)

    with app.app_context():
        assert Report.query.count() == 0


def test_duplicate_report_rejected(client, db, app):
    register(client, username="sellerD")
    login(client, username="sellerD")
    _create_product(client, name="중복신고상품")
    product_id = _get_product_id(app, "중복신고상품")
    _logout(client)

    register(client, username="reporterE")
    login(client, username="reporterE")
    _report(client, "product", product_id)
    resp = _report(client, "product", product_id)
    assert "이미 신고한 대상입니다" in resp.get_data(as_text=True)

    with app.app_context():
        assert Report.query.filter_by(target_type="product", target_id=product_id).count() == 1
        product = Product.query.filter_by(id=product_id).first()
        assert product.report_count == 1


def test_product_auto_blocked_after_threshold_reports(client, db, app):
    register(client, username="sellerE")
    login(client, username="sellerE")
    _create_product(client, name="차단될상품")
    product_id = _get_product_id(app, "차단될상품")
    _logout(client)

    for i in range(REPORT_BLOCK_THRESHOLD):
        register(client, username=f"blockreporter{i}")
        login(client, username=f"blockreporter{i}")
        _report(client, "product", product_id)
        _logout(client)

    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        assert product.report_count == REPORT_BLOCK_THRESHOLD
        assert product.status == ProductStatus.BLOCKED

    # blocked products no longer appear in the browse list or search
    register(client, username="browsingUser")
    login(client, username="browsingUser")
    list_resp = client.get("/products")
    assert "차단될상품" not in list_resp.get_data(as_text=True)
    search_resp = client.get("/products/search?q=차단될상품")
    assert "검색 결과가 없습니다" in search_resp.get_data(as_text=True)


def test_user_auto_suspended_after_threshold_reports(client, db, app):
    from tests.helpers import VALID_PASSWORD

    register(client, username="targetToSuspend")  # not logged in -- registering doesn't authenticate
    target_id = _get_user_id(app, "targetToSuspend")

    for i in range(REPORT_BLOCK_THRESHOLD):
        register(client, username=f"suspendreporter{i}")
        login(client, username=f"suspendreporter{i}")
        _report(client, "user", target_id)
        _logout(client)

    with app.app_context():
        user = User.query.filter_by(id=target_id).first()
        assert user.report_count == REPORT_BLOCK_THRESHOLD
        assert user.status == UserStatus.SUSPENDED

    # a suspended account can no longer log in
    resp = login(client, username="targetToSuspend", password=VALID_PASSWORD)
    assert resp.status_code == 200
    assert "휴면 처리된 계정입니다" in resp.get_data(as_text=True)
