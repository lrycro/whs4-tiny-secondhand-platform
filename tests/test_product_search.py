from models import Product, ProductStatus
from tests.helpers import extract_csrf, login, register, valid_photo


def _create_product(client, name, description=""):
    resp = client.get("/products/new")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/products/new",
        data={
            "name": name,
            "description": description,
            "price": "1000",
            "csrf_token": token,
            "photo": valid_photo(),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_search_requires_login(client, db):
    resp = client.get("/products/search?q=test", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_search_by_name_keyword(client, db):
    register(client, username="searcher1")
    login(client, username="searcher1")
    _create_product(client, "빨간 자전거")
    _create_product(client, "파란 자동차")

    resp = client.get("/products/search?q=자전거")
    html = resp.get_data(as_text=True)
    assert "빨간 자전거" in html
    assert "파란 자동차" not in html


def test_search_by_description_keyword(client, db):
    register(client, username="searcher2")
    login(client, username="searcher2")
    _create_product(client, "상품A", description="거의 새 상품입니다")
    _create_product(client, "상품B", description="사용감 있음")

    resp = client.get("/products/search?q=새 상품")
    html = resp.get_data(as_text=True)
    assert "상품A" in html
    assert "상품B" not in html


def test_search_no_results(client, db):
    register(client, username="searcher3")
    login(client, username="searcher3")
    _create_product(client, "노트북")

    resp = client.get("/products/search?q=존재하지않는검색어")
    html = resp.get_data(as_text=True)
    assert "검색 결과가 없습니다" in html
    assert "노트북" not in html


def test_search_empty_query_returns_all_active(client, db):
    register(client, username="searcher4")
    login(client, username="searcher4")
    _create_product(client, "상품1")
    _create_product(client, "상품2")

    resp = client.get("/products/search?q=")
    html = resp.get_data(as_text=True)
    assert "상품1" in html
    assert "상품2" in html


def test_search_escapes_like_wildcards(client, db):
    register(client, username="searcher5")
    login(client, username="searcher5")
    _create_product(client, "테스트_언더바상품")
    _create_product(client, "일반상품")

    # an unescaped LIKE pattern for "_" (%_%) matches ANY non-empty string,
    # which would incorrectly return every product
    resp = client.get("/products/search?q=_")
    html = resp.get_data(as_text=True)
    assert "테스트_언더바상품" in html
    assert "일반상품" not in html


def test_search_excludes_blocked_products(client, db, app):
    register(client, username="searcher6")
    login(client, username="searcher6")
    _create_product(client, "차단될상품")

    with app.app_context():
        product = Product.query.filter_by(name="차단될상품").first()
        product.status = ProductStatus.BLOCKED
        db.session.commit()

    resp = client.get("/products/search?q=차단될상품")
    html = resp.get_data(as_text=True)
    assert "검색 결과가 없습니다" in html
    assert f">차단될상품</a>" not in html
