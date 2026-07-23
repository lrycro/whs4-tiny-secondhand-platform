from extensions import socketio
from models import ChatThread, GlobalMessage, Message, Product, User
from tests.helpers import extract_csrf, login, register


def _logout(client):
    token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": token}, follow_redirects=True)


def _user_id(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().id


def _create_product(client, name="채팅용상품", price=1000):
    resp = client.get("/products/new")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/products/new",
        data={"name": name, "description": "설명", "price": str(price), "csrf_token": token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _product_id(app, name):
    with app.app_context():
        return Product.query.filter_by(name=name).first().id


def test_dm_page_requires_login(client, db):
    resp = client.get("/chat/1/2", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_dm_page_with_self_redirects(client, db, app):
    register(client, username="selfchat")
    login(client, username="selfchat")
    _create_product(client, name="셀프상품")
    product_id = _product_id(app, "셀프상품")
    my_id = _user_id(app, "selfchat")

    resp = client.get(f"/chat/{product_id}/{my_id}", follow_redirects=True)
    assert "본인과는 채팅할 수 없습니다" in resp.get_data(as_text=True)


def test_dm_page_with_nonexistent_product_404s(client, db):
    register(client, username="dmviewer1")
    login(client, username="dmviewer1")

    resp = client.get("/chat/999999/888888")
    assert resp.status_code == 404


def test_dm_page_with_nonexistent_user_404s(client, db, app):
    register(client, username="dmviewer2")
    login(client, username="dmviewer2")
    _create_product(client, name="상품404테스트")
    product_id = _product_id(app, "상품404테스트")

    resp = client.get(f"/chat/{product_id}/999999")
    assert resp.status_code == 404


def test_dm_page_rejects_pair_with_neither_party_as_seller(client, db, app):
    register(client, username="sellerX")
    login(client, username="sellerX")
    _create_product(client, name="제3자상품")
    product_id = _product_id(app, "제3자상품")
    _logout(client)

    register(client, username="randomBuyer1")
    register(client, username="randomBuyer2")
    login(client, username="randomBuyer1")
    buyer2_id = _user_id(app, "randomBuyer2")

    # neither randomBuyer1 (current user) nor randomBuyer2 (other_user_id) is the seller
    resp = client.get(f"/chat/{product_id}/{buyer2_id}")
    assert resp.status_code == 403


def test_dm_creates_and_reuses_thread(client, db, app):
    register(client, username="sellerY")
    login(client, username="sellerY")
    _create_product(client, name="쓰레드상품")
    product_id = _product_id(app, "쓰레드상품")
    seller_id = _user_id(app, "sellerY")
    _logout(client)

    register(client, username="buyerY")
    login(client, username="buyerY")
    buyer_id = _user_id(app, "buyerY")

    client.get(f"/chat/{product_id}/{seller_id}")
    with app.app_context():
        assert ChatThread.query.filter_by(product_id=product_id, buyer_id=buyer_id).count() == 1

    # visiting again must NOT create a second thread
    client.get(f"/chat/{product_id}/{seller_id}")
    with app.app_context():
        assert ChatThread.query.filter_by(product_id=product_id, buyer_id=buyer_id).count() == 1


def test_dm_page_shows_history(client, db, app):
    register(client, username="sellerZ")
    login(client, username="sellerZ")
    _create_product(client, name="히스토리상품")
    product_id = _product_id(app, "히스토리상품")
    seller_id = _user_id(app, "sellerZ")
    _logout(client)

    register(client, username="buyerZ")
    login(client, username="buyerZ")
    buyer_id = _user_id(app, "buyerZ")

    # first visit creates the thread
    client.get(f"/chat/{product_id}/{seller_id}")

    with app.app_context():
        thread = ChatThread.query.filter_by(product_id=product_id, buyer_id=buyer_id).first()
        db.session.add(Message(sender_id=seller_id, thread_id=thread.id, content="안녕하세요 구매자님"))
        db.session.commit()

    resp = client.get(f"/chat/{product_id}/{seller_id}")
    html = resp.get_data(as_text=True)
    assert "안녕하세요 구매자님" in html
    assert "sellerZ" in html
    assert "히스토리상품" in html


def test_unauthenticated_socket_connection_rejected(client, db, app):
    anon_client = app.test_client()
    sio_client = socketio.test_client(app, flask_test_client=anon_client)
    assert sio_client.is_connected() is False


def test_global_chat_round_trip(client, db, app):
    register(client, username="globalchat1")
    login(client, username="globalchat1")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {})
    sio_client.emit("send_message", {"content": "안녕하세요 전체 채팅"})

    received = sio_client.get_received()
    assert len(received) == 1
    event = received[0]
    assert event["name"] == "receive_message"
    payload = event["args"][0]
    assert payload["content"] == "안녕하세요 전체 채팅"
    assert payload["thread_id"] is None
    assert payload["sender_username"] == "globalchat1"

    with app.app_context():
        saved = GlobalMessage.query.filter_by(content="안녕하세요 전체 채팅").first()
        assert saved is not None
        assert saved.sender_id == _user_id(app, "globalchat1")


def test_global_chat_message_history_is_escaped_on_render(client, db):
    register(client, username="globalxss")
    login(client, username="globalxss")

    sio_client = socketio.test_client(client.application, flask_test_client=client)
    sio_client.emit("join_room", {})
    sio_client.emit("send_message", {"content": "<script>alert('xss-global')</script>"})

    resp = client.get("/products")
    html = resp.get_data(as_text=True)
    assert "<script>alert('xss-global')</script>" not in html
    assert "&lt;script&gt;alert(&#39;xss-global&#39;)&lt;/script&gt;" in html


def test_global_and_dm_chat_are_isolated(client, db, app):
    register(client, username="isoSeller")
    login(client, username="isoSeller")
    isoseller_client = client
    _create_product(client, name="격리테스트상품")
    product_id = _product_id(app, "격리테스트상품")
    seller_id = _user_id(app, "isoSeller")

    buyer_client = app.test_client()
    register(buyer_client, username="isoBuyer")
    login(buyer_client, username="isoBuyer")
    buyer_client.get(f"/chat/{product_id}/{seller_id}")
    with app.app_context():
        thread_id = ChatThread.query.filter_by(product_id=product_id).first().id

    sio_seller = socketio.test_client(app, flask_test_client=isoseller_client)
    sio_buyer = socketio.test_client(app, flask_test_client=buyer_client)

    # both join the DM thread only, NOT the global room
    sio_seller.emit("join_room", {"thread_id": thread_id})
    sio_buyer.emit("join_room", {"thread_id": thread_id})

    # a third, unrelated user posts to the GLOBAL room
    outsider_client = app.test_client()
    register(outsider_client, username="isoOutsider")
    login(outsider_client, username="isoOutsider")
    sio_outsider = socketio.test_client(app, flask_test_client=outsider_client)
    sio_outsider.emit("join_room", {})
    sio_outsider.emit("send_message", {"content": "전체채팅 메시지"})
    sio_outsider.get_received()  # drain the outsider's own global broadcast (self-inclusive)

    # neither DM participant should have received the global broadcast
    assert sio_seller.get_received() == []
    assert sio_buyer.get_received() == []

    # and a DM message must not leak into the global room either
    sio_seller.emit("send_message", {"thread_id": thread_id, "content": "DM 메시지"})
    assert sio_outsider.get_received() == []


def test_dm_message_reaches_both_participants_only(client, db, app):
    register(client, username="dmAlice")
    login(client, username="dmAlice")
    alice_client = client
    _create_product(client, name="알리스상품")
    product_id = _product_id(app, "알리스상품")
    alice_id = _user_id(app, "dmAlice")

    bob_client = app.test_client()
    register(bob_client, username="dmBob")
    login(bob_client, username="dmBob")
    bob_id = _user_id(app, "dmBob")

    carol_client = app.test_client()
    register(carol_client, username="dmCarol")
    login(carol_client, username="dmCarol")

    # bob (buyer) and alice (seller) open the thread for this product
    bob_client.get(f"/chat/{product_id}/{alice_id}")
    with app.app_context():
        thread = ChatThread.query.filter_by(product_id=product_id, buyer_id=bob_id).first()
        thread_id = thread.id

    sio_alice = socketio.test_client(app, flask_test_client=alice_client)
    sio_bob = socketio.test_client(app, flask_test_client=bob_client)
    sio_carol = socketio.test_client(app, flask_test_client=carol_client)

    sio_alice.emit("join_room", {"thread_id": thread_id})
    sio_bob.emit("join_room", {"thread_id": thread_id})
    # carol is neither the buyer nor the seller on this thread -- must be rejected
    sio_carol.emit("join_room", {"thread_id": thread_id})

    sio_bob.emit("send_message", {"thread_id": thread_id, "content": "비밀 메시지"})

    alice_received = sio_alice.get_received()
    bob_received = sio_bob.get_received()
    carol_received = sio_carol.get_received()

    assert len(alice_received) == 1
    assert alice_received[0]["args"][0]["content"] == "비밀 메시지"
    assert len(bob_received) == 1
    assert bob_received[0]["args"][0]["content"] == "비밀 메시지"
    assert carol_received == []

    with app.app_context():
        saved = Message.query.filter_by(content="비밀 메시지").first()
        assert saved.thread_id == thread_id


def test_non_participant_join_and_send_are_ignored(client, db, app):
    register(client, username="threadOwnerSeller")
    login(client, username="threadOwnerSeller")
    _create_product(client, name="비참여자상품")
    product_id = _product_id(app, "비참여자상품")
    seller_id = _user_id(app, "threadOwnerSeller")
    _logout(client)

    register(client, username="threadOwnerBuyer")
    login(client, username="threadOwnerBuyer")
    client.get(f"/chat/{product_id}/{seller_id}")
    _logout(client)

    with app.app_context():
        thread_id = ChatThread.query.filter_by(product_id=product_id).first().id

    register(client, username="outsider")
    login(client, username="outsider")

    sio_outsider = socketio.test_client(client.application, flask_test_client=client)
    sio_outsider.emit("join_room", {"thread_id": thread_id})
    sio_outsider.emit("send_message", {"thread_id": thread_id, "content": "몰래 보내기"})

    assert sio_outsider.get_received() == []
    with app.app_context():
        assert Message.query.filter_by(content="몰래 보내기").first() is None


def test_send_message_with_nonexistent_thread_is_ignored(client, db):
    register(client, username="ghostthreaduser")
    login(client, username="ghostthreaduser")

    sio_client = socketio.test_client(client.application, flask_test_client=client)
    sio_client.emit("send_message", {"thread_id": 999999, "content": "hello ghost"})

    assert sio_client.get_received() == []
    with client.application.app_context():
        assert Message.query.filter_by(content="hello ghost").first() is None


def test_empty_message_is_ignored(client, db, app):
    register(client, username="sellerEmpty")
    login(client, username="sellerEmpty")
    _create_product(client, name="빈메시지상품")
    product_id = _product_id(app, "빈메시지상품")
    seller_id = _user_id(app, "sellerEmpty")
    _logout(client)

    register(client, username="buyerEmpty")
    login(client, username="buyerEmpty")
    client.get(f"/chat/{product_id}/{seller_id}")
    with app.app_context():
        thread_id = ChatThread.query.filter_by(product_id=product_id).first().id

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {"thread_id": thread_id})
    sio_client.emit("send_message", {"thread_id": thread_id, "content": "   "})

    assert sio_client.get_received() == []
    with app.app_context():
        assert Message.query.count() == 0


def test_oversized_message_rejected(client, db, app):
    register(client, username="sellerLong")
    login(client, username="sellerLong")
    _create_product(client, name="긴메시지상품")
    product_id = _product_id(app, "긴메시지상품")
    seller_id = _user_id(app, "sellerLong")
    _logout(client)

    register(client, username="buyerLong")
    login(client, username="buyerLong")
    client.get(f"/chat/{product_id}/{seller_id}")
    with app.app_context():
        thread_id = ChatThread.query.filter_by(product_id=product_id).first().id

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {"thread_id": thread_id})
    sio_client.emit("send_message", {"thread_id": thread_id, "content": "x" * 1001})

    received = sio_client.get_received()
    assert len(received) == 1
    assert received[0]["name"] == "chat_error"
    with app.app_context():
        assert Message.query.count() == 0


def test_rate_limit_blocks_rapid_messages(client, db, app):
    register(client, username="sellerSpam")
    login(client, username="sellerSpam")
    _create_product(client, name="스팸상품")
    product_id = _product_id(app, "스팸상품")
    seller_id = _user_id(app, "sellerSpam")
    _logout(client)

    register(client, username="spammer")
    login(client, username="spammer")
    client.get(f"/chat/{product_id}/{seller_id}")
    with app.app_context():
        thread_id = ChatThread.query.filter_by(product_id=product_id).first().id

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {"thread_id": thread_id})

    for i in range(8):
        sio_client.emit("send_message", {"thread_id": thread_id, "content": f"spam {i}"})

    received = sio_client.get_received()
    errors = [e for e in received if e["name"] == "chat_error"]
    messages = [e for e in received if e["name"] == "receive_message"]

    assert len(errors) > 0
    assert len(messages) == 5  # RATE_LIMIT_MAX_MESSAGES


def test_chat_message_history_is_escaped_on_render(client, db, app):
    register(client, username="sellerXss")
    login(client, username="sellerXss")
    _create_product(client, name="XSS채팅상품")
    product_id = _product_id(app, "XSS채팅상품")
    seller_id = _user_id(app, "sellerXss")
    _logout(client)

    register(client, username="buyerXss")
    login(client, username="buyerXss")
    client.get(f"/chat/{product_id}/{seller_id}")
    with app.app_context():
        thread_id = ChatThread.query.filter_by(product_id=product_id).first().id

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {"thread_id": thread_id})
    sio_client.emit("send_message", {"thread_id": thread_id, "content": "<script>alert('xss-chat')</script>"})

    resp = client.get(f"/chat/{product_id}/{seller_id}")
    html = resp.get_data(as_text=True)
    assert "<script>alert('xss-chat')</script>" not in html
    assert "&lt;script&gt;alert(&#39;xss-chat&#39;)&lt;/script&gt;" in html


def test_chat_list_requires_login(client, db):
    resp = client.get("/chat", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_chat_list_shows_my_threads_for_both_roles(client, db, app):
    register(client, username="listSeller")
    login(client, username="listSeller")
    _create_product(client, name="목록상품")
    product_id = _product_id(app, "목록상품")
    seller_id = _user_id(app, "listSeller")
    _logout(client)

    register(client, username="listBuyer")
    login(client, username="listBuyer")
    client.get(f"/chat/{product_id}/{seller_id}")

    # buyer's chat list shows the thread
    resp = client.get("/chat")
    html = resp.get_data(as_text=True)
    assert "목록상품" in html
    assert "listSeller" in html
    _logout(client)

    # seller's chat list also shows the same thread
    login(client, username="listSeller")
    resp2 = client.get("/chat")
    html2 = resp2.get_data(as_text=True)
    assert "목록상품" in html2
    assert "listBuyer" in html2


def test_chat_list_does_not_show_unrelated_threads(client, db, app):
    register(client, username="otherSeller")
    login(client, username="otherSeller")
    _create_product(client, name="무관상품")
    product_id = _product_id(app, "무관상품")
    seller_id = _user_id(app, "otherSeller")
    _logout(client)

    register(client, username="otherBuyer")
    login(client, username="otherBuyer")
    client.get(f"/chat/{product_id}/{seller_id}")
    _logout(client)

    register(client, username="unrelatedUser")
    login(client, username="unrelatedUser")
    resp = client.get("/chat")
    assert "무관상품" not in resp.get_data(as_text=True)
