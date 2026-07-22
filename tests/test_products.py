import io

from models import Product
from tests.helpers import extract_csrf, login, register


def _create_product(client, name="중고 자전거", description="거의 새것", price=15000, photo=None):
    resp = client.get("/products/new")
    token = extract_csrf(resp.get_data(as_text=True))
    data = {"name": name, "description": description, "price": str(price), "csrf_token": token}
    if photo is not None:
        data["photo"] = photo
    return client.post(
        "/products/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _logout(client):
    token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": token}, follow_redirects=True)


def test_product_list_requires_login(client, db):
    resp = client.get("/products", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_product_new_requires_login(client, db):
    resp = client.get("/products/new", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_create_product_success(client, db):
    register(client, username="seller1")
    login(client, username="seller1")

    resp = _create_product(client)
    assert "상품이 등록되었습니다" in resp.get_data(as_text=True)
    assert "중고 자전거" in resp.get_data(as_text=True)

    product = Product.query.filter_by(name="중고 자전거").first()
    assert product is not None
    assert product.price == 15000
    assert product.seller.username == "seller1"

    list_resp = client.get("/products")
    assert "중고 자전거" in list_resp.get_data(as_text=True)


def test_create_product_missing_name_rejected(client, db):
    register(client, username="seller2")
    login(client, username="seller2")

    resp = _create_product(client, name="")
    assert "상품명을 입력해주세요" in resp.get_data(as_text=True)
    assert Product.query.count() == 0


def test_create_product_negative_price_rejected(client, db):
    register(client, username="seller3")
    login(client, username="seller3")

    resp = _create_product(client, price=-100)
    assert "가격은 0 이상이어야 합니다" in resp.get_data(as_text=True)
    assert Product.query.count() == 0


def test_create_product_bad_photo_extension_rejected(client, db):
    register(client, username="seller4")
    login(client, username="seller4")

    resp = _create_product(client, photo=(io.BytesIO(b"not an image"), "malware.exe"))
    assert "jpg, jpeg, png, gif, webp 파일만 업로드할 수 있습니다" in resp.get_data(as_text=True)
    assert Product.query.count() == 0


def test_create_product_valid_photo_saved(client, db, app):
    register(client, username="seller5")
    login(client, username="seller5")

    resp = _create_product(client, photo=(io.BytesIO(b"\x89PNG\r\n\x1a\n fake"), "photo.png"))
    assert "상품이 등록되었습니다" in resp.get_data(as_text=True)

    product = Product.query.filter_by(seller_id=1).first()
    assert product.image_filename is not None
    assert product.image_filename.endswith(".png")

    import os

    with app.app_context():
        upload_dir = app.config["PRODUCT_UPLOAD_DIR"]
    saved_path = os.path.join(upload_dir, product.image_filename)
    assert os.path.exists(saved_path)
    os.remove(saved_path)


def test_product_detail_shows_seller_and_owner_controls(client, db):
    register(client, username="ownerx")
    login(client, username="ownerx")
    _create_product(client, name="상세보기테스트")
    product = Product.query.filter_by(name="상세보기테스트").first()

    resp = client.get(f"/products/{product.id}")
    html = resp.get_data(as_text=True)
    assert "ownerx" in html
    assert "수정" in html
    assert "삭제" in html


def test_nonexistent_product_returns_404(client, db):
    register(client, username="lookup404")
    login(client, username="lookup404")
    resp = client.get("/products/999999")
    assert resp.status_code == 404


def test_owner_can_edit_product(client, db):
    register(client, username="editowner")
    login(client, username="editowner")
    _create_product(client, name="원래이름")
    product = Product.query.filter_by(name="원래이름").first()

    token = extract_csrf(client.get(f"/products/{product.id}/edit").get_data(as_text=True))
    resp = client.post(
        f"/products/{product.id}/edit",
        data={"name": "수정된이름", "description": "수정됨", "price": "20000", "csrf_token": token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "상품 정보가 수정되었습니다" in resp.get_data(as_text=True)

    updated = Product.query.filter_by(id=product.id).first()
    assert updated.name == "수정된이름"
    assert updated.price == 20000


def test_non_owner_cannot_edit_product(client, db):
    register(client, username="idorOwnerA")
    login(client, username="idorOwnerA")
    _create_product(client, name="A의상품")
    product = Product.query.filter_by(name="A의상품").first()
    _logout(client)

    register(client, username="idorAttackerB")
    login(client, username="idorAttackerB")

    # GET the edit form directly (not through owner's link) -- must be forbidden
    resp = client.get(f"/products/{product.id}/edit")
    assert resp.status_code == 403

    # even a forged POST must be rejected server-side, regardless of client UI
    token = extract_csrf(client.get("/").get_data(as_text=True))
    post_resp = client.post(
        f"/products/{product.id}/edit",
        data={"name": "해킹시도", "description": "x", "price": "1", "csrf_token": token},
        content_type="multipart/form-data",
    )
    assert post_resp.status_code == 403

    unchanged = Product.query.filter_by(id=product.id).first()
    assert unchanged.name == "A의상품"


def test_non_owner_cannot_delete_product(client, db):
    register(client, username="idorOwnerC")
    login(client, username="idorOwnerC")
    _create_product(client, name="C의상품")
    product = Product.query.filter_by(name="C의상품").first()
    _logout(client)

    register(client, username="idorAttackerD")
    login(client, username="idorAttackerD")

    token = extract_csrf(client.get("/").get_data(as_text=True))
    resp = client.post(f"/products/{product.id}/delete", data={"csrf_token": token})
    assert resp.status_code == 403
    assert Product.query.filter_by(id=product.id).first() is not None


def test_owner_can_delete_product(client, db):
    register(client, username="deleteowner")
    login(client, username="deleteowner")
    _create_product(client, name="삭제될상품")
    product = Product.query.filter_by(name="삭제될상품").first()

    token = extract_csrf(client.get("/").get_data(as_text=True))
    resp = client.post(
        f"/products/{product.id}/delete", data={"csrf_token": token}, follow_redirects=True
    )
    assert "상품이 삭제되었습니다" in resp.get_data(as_text=True)
    assert Product.query.filter_by(id=product.id).first() is None


def test_mypage_lists_only_own_products(client, db, app):
    register(client, username="ownerE")
    login(client, username="ownerE")
    _create_product(client, name="E의상품")
    _logout(client)

    register(client, username="ownerF")
    login(client, username="ownerF")
    _create_product(client, name="F의상품")

    resp = client.get("/mypage")
    html = resp.get_data(as_text=True)
    assert "F의상품" in html
    assert "E의상품" not in html
