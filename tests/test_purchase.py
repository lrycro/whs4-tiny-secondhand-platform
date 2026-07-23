import threading

from extensions import db
from models import ChatThread, MAX_BALANCE, Product, Transaction, User
from tests.helpers import extract_csrf, login, register, valid_photo


def _create_product(client, name="구매테스트상품", price=10000):
    resp = client.get("/products/new")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/products/new",
        data={
            "name": name,
            "description": "d",
            "price": str(price),
            "csrf_token": token,
            "photo": valid_photo(),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _product_id(app, name):
    with app.app_context():
        return Product.query.filter_by(name=name).first().id


def _set_balance(app, username, amount):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        user.balance = amount
        db.session.commit()


def _get_balance(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().balance


def _purchase(client, product_id):
    resp = client.get(f"/products/{product_id}")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        f"/products/{product_id}/purchase",
        data={"csrf_token": token},
        follow_redirects=True,
    )


def test_purchase_requires_login(client, db, app):
    register(client, username="pseller1")
    login(client, username="pseller1")
    _create_product(client, name="상품1", price=5000)
    product_id = _product_id(app, "상품1")

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    # a valid (session-bound) CSRF token even while logged out, to isolate the
    # @login_required check from CSRF validation (both would otherwise reject the
    # request, and a missing token alone would 400 before login is ever checked)
    token = extract_csrf(client.get("/login").get_data(as_text=True))
    resp = client.post(
        f"/products/{product_id}/purchase", data={"csrf_token": token}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_purchase_success(client, db, app):
    register(client, username="pseller2")
    login(client, username="pseller2")
    _create_product(client, name="상품2", price=20000)
    product_id = _product_id(app, "상품2")

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    register(client, username="pbuyer2")
    login(client, username="pbuyer2")
    _set_balance(app, "pbuyer2", 50000)

    resp = _purchase(client, product_id)
    assert "구매가 완료되었습니다" in resp.get_data(as_text=True)

    assert _get_balance(app, "pbuyer2") == 30000
    assert _get_balance(app, "pseller2") == 20000

    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        buyer = User.query.filter_by(username="pbuyer2").first()
        assert product.sale_status.value == "sold"
        assert product.buyer_id == buyer.id

        tx = Transaction.query.filter_by(product_id=product_id).first()
        assert tx is not None
        assert tx.amount == 20000
        assert tx.receiver_id == User.query.filter_by(username="pseller2").first().id

        thread = ChatThread.query.filter_by(product_id=product_id, buyer_id=buyer.id).first()
        assert thread is not None

    detail_html = client.get(f"/products/{product_id}").get_data(as_text=True)
    assert "거래완료" in detail_html
    assert "구매자:" in detail_html
    assert "pbuyer2" in detail_html
    assert 'name="sale_status"' not in detail_html  # buyer isn't the seller
    assert "구매하기" not in detail_html  # already sold, button gone


def test_purchase_reuses_existing_chat_thread(client, db, app):
    register(client, username="pseller3")
    login(client, username="pseller3")
    _create_product(client, name="상품3", price=15000)
    product_id = _product_id(app, "상품3")
    seller_id = None
    with app.app_context():
        seller_id = User.query.filter_by(username="pseller3").first().id

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    register(client, username="pbuyer3")
    login(client, username="pbuyer3")
    _set_balance(app, "pbuyer3", 50000)

    # buyer chats with seller about this product BEFORE purchasing
    client.get(f"/chat/{product_id}/{seller_id}")

    with app.app_context():
        buyer_id = User.query.filter_by(username="pbuyer3").first().id
        existing_thread_id = ChatThread.query.filter_by(product_id=product_id, buyer_id=buyer_id).first().id

    _purchase(client, product_id)

    with app.app_context():
        threads = ChatThread.query.filter_by(product_id=product_id, buyer_id=buyer_id).all()
        assert len(threads) == 1
        assert threads[0].id == existing_thread_id


def test_purchase_insufficient_balance_rejected(client, db, app):
    register(client, username="pseller4")
    login(client, username="pseller4")
    _create_product(client, name="상품4", price=99999)
    product_id = _product_id(app, "상품4")

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    register(client, username="pbuyer4")
    login(client, username="pbuyer4")
    _set_balance(app, "pbuyer4", 1000)

    resp = _purchase(client, product_id)
    assert "잔액이 부족합니다" in resp.get_data(as_text=True)

    assert _get_balance(app, "pbuyer4") == 1000
    assert _get_balance(app, "pseller4") == 0
    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        assert product.sale_status.value == "on_sale"
        assert product.buyer_id is None
        assert Transaction.query.filter_by(product_id=product_id).count() == 0


def test_purchase_already_sold_rejected(client, db, app):
    register(client, username="pseller5")
    login(client, username="pseller5")
    _create_product(client, name="상품5", price=5000)
    product_id = _product_id(app, "상품5")

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    register(client, username="pbuyer5a")
    login(client, username="pbuyer5a")
    _set_balance(app, "pbuyer5a", 10000)
    _purchase(client, product_id)  # first buyer succeeds

    logout_token2 = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token2}, follow_redirects=True)

    register(client, username="pbuyer5b")
    login(client, username="pbuyer5b")
    _set_balance(app, "pbuyer5b", 10000)

    resp = _purchase(client, product_id)
    assert "이미 판매된 상품입니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "pbuyer5b") == 10000  # untouched

    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        buyer_a = User.query.filter_by(username="pbuyer5a").first()
        assert product.buyer_id == buyer_a.id  # still the first buyer
        assert Transaction.query.filter_by(product_id=product_id).count() == 1


def test_purchase_reserved_product_rejected(client, db, app):
    register(client, username="pseller6")
    login(client, username="pseller6")
    _create_product(client, name="상품6", price=5000)
    product_id = _product_id(app, "상품6")

    token = extract_csrf(client.get(f"/products/{product_id}").get_data(as_text=True))
    client.post(
        f"/products/{product_id}/status",
        data={"sale_status": "reserved", "csrf_token": token},
        follow_redirects=True,
    )

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    register(client, username="pbuyer6")
    login(client, username="pbuyer6")
    _set_balance(app, "pbuyer6", 10000)

    resp = _purchase(client, product_id)
    assert "예약 중인 상품이라 구매할 수 없습니다" in resp.get_data(as_text=True)
    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        assert product.sale_status.value == "reserved"
        assert product.buyer_id is None


def test_purchase_own_product_rejected(client, db, app):
    register(client, username="pseller7")
    login(client, username="pseller7")
    _create_product(client, name="상품7", price=5000)
    product_id = _product_id(app, "상품7")
    _set_balance(app, "pseller7", 10000)

    # button must not be rendered for the owner
    detail_html = client.get(f"/products/{product_id}").get_data(as_text=True)
    assert "구매하기" not in detail_html

    # forged direct POST must still be rejected server-side (IDOR)
    token = extract_csrf(detail_html)
    resp = client.post(
        f"/products/{product_id}/purchase", data={"csrf_token": token}
    )
    assert resp.status_code == 403

    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        assert product.sale_status.value == "on_sale"
        assert product.buyer_id is None


def test_purchase_seller_balance_cap_exceeded_rejected(client, db, app):
    register(client, username="pseller8")
    login(client, username="pseller8")
    _create_product(client, name="상품8", price=5000)
    product_id = _product_id(app, "상품8")
    _set_balance(app, "pseller8", MAX_BALANCE - 1000)

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    register(client, username="pbuyer8")
    login(client, username="pbuyer8")
    _set_balance(app, "pbuyer8", 10000)

    resp = _purchase(client, product_id)
    assert "판매자의 보유 잔액이 상한을 초과하게 되어 구매할 수 없습니다" in resp.get_data(as_text=True)

    assert _get_balance(app, "pbuyer8") == 10000
    assert _get_balance(app, "pseller8") == MAX_BALANCE - 1000
    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        assert product.sale_status.value == "on_sale"
        assert product.buyer_id is None


def test_purchase_concurrent_only_one_winner(client, db, app):
    register(client, username="pracesell")
    login(client, username="pracesell")
    _create_product(client, name="동시구매테스트상품", price=5000)
    product_id = _product_id(app, "동시구매테스트상품")

    client_a = app.test_client()
    client_b = app.test_client()
    register(client_a, username="pracebuyerA")
    register(client_b, username="pracebuyerB")
    login(client_a, username="pracebuyerA")
    login(client_b, username="pracebuyerB")
    _set_balance(app, "pracebuyerA", 10000)
    _set_balance(app, "pracebuyerB", 10000)

    token_a = extract_csrf(client_a.get(f"/products/{product_id}").get_data(as_text=True))
    token_b = extract_csrf(client_b.get(f"/products/{product_id}").get_data(as_text=True))

    barrier = threading.Barrier(2)
    results = {}

    def attempt(name, cl, token):
        barrier.wait()
        resp = cl.post(
            f"/products/{product_id}/purchase",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        results[name] = resp.get_data(as_text=True)

    t1 = threading.Thread(target=attempt, args=("A", client_a, token_a))
    t2 = threading.Thread(target=attempt, args=("B", client_b, token_b))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    successes = sum(1 for text in results.values() if "구매가 완료되었습니다" in text)
    already_sold = sum(1 for text in results.values() if "이미 판매된 상품입니다" in text)

    assert successes == 1, f"expected exactly one winner, got results={results}"
    assert already_sold == 1

    with app.app_context():
        product = Product.query.filter_by(id=product_id).first()
        buyer_a = User.query.filter_by(username="pracebuyerA").first()
        buyer_b = User.query.filter_by(username="pracebuyerB").first()
        assert product.sale_status.value == "sold"
        assert product.buyer_id in (buyer_a.id, buyer_b.id)
        assert Transaction.query.filter_by(product_id=product_id).count() == 1

    total_balance = _get_balance(app, "pracebuyerA") + _get_balance(app, "pracebuyerB")
    assert total_balance == 15000  # exactly one 5,000-price purchase happened


def test_purchase_shows_in_transaction_history_for_both_parties(client, db, app):
    register(client, username="pseller9")
    login(client, username="pseller9")
    _create_product(client, name="거래내역용상품", price=7000)
    product_id = _product_id(app, "거래내역용상품")

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    register(client, username="pbuyer9")
    login(client, username="pbuyer9")
    _set_balance(app, "pbuyer9", 20000)
    _purchase(client, product_id)

    buyer_html = client.get("/mypage/transactions").get_data(as_text=True)
    assert 'pseller9님에게서 "거래내역용상품" 구매' in buyer_html
    assert "-7,000원" in buyer_html

    logout_token2 = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token2}, follow_redirects=True)

    login(client, username="pseller9")
    seller_html = client.get("/mypage/transactions").get_data(as_text=True)
    assert 'pbuyer9님에게 "거래내역용상품" 판매' in seller_html
    assert "+7,000원" in seller_html
