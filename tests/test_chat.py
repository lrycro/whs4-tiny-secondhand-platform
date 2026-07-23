from extensions import socketio
from models import Message, User
from tests.helpers import extract_csrf, login, register


def _logout(client):
    token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": token}, follow_redirects=True)


def _user_id(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().id


def test_dm_page_requires_login(client, db):
    resp = client.get("/chat/1", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_dm_page_with_self_redirects(client, db, app):
    register(client, username="selfchat")
    login(client, username="selfchat")
    my_id = _user_id(app, "selfchat")

    resp = client.get(f"/chat/{my_id}", follow_redirects=True)
    assert "본인과는 채팅할 수 없습니다" in resp.get_data(as_text=True)


def test_dm_page_with_nonexistent_user_404s(client, db):
    register(client, username="dmviewer")
    login(client, username="dmviewer")

    resp = client.get("/chat/999999")
    assert resp.status_code == 404


def test_dm_page_shows_history(client, db, app):
    register(client, username="dmhistoryA")
    login(client, username="dmhistoryA")
    a_id = _user_id(app, "dmhistoryA")
    _logout(client)

    register(client, username="dmhistoryB")
    login(client, username="dmhistoryB")
    b_id = _user_id(app, "dmhistoryB")

    with app.app_context():
        lo, hi = sorted((a_id, b_id))
        db.session.add(Message(sender_id=b_id, room=f"dm_{lo}_{hi}", content="안녕하세요 A님"))
        db.session.commit()

    resp = client.get(f"/chat/{a_id}")
    html = resp.get_data(as_text=True)
    assert "안녕하세요 A님" in html
    assert "dmhistoryB" in html


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
    assert payload["room"] == "global"
    assert payload["sender_username"] == "globalchat1"

    with app.app_context():
        saved = Message.query.filter_by(room="global", content="안녕하세요 전체 채팅").first()
        assert saved is not None
        assert saved.sender_id == _user_id(app, "globalchat1")


def test_dm_message_reaches_both_participants_only(client, db, app):
    register(client, username="dmAlice")
    login(client, username="dmAlice")
    alice_client = client
    alice_id = _user_id(app, "dmAlice")

    bob_client = app.test_client()
    register(bob_client, username="dmBob")
    login(bob_client, username="dmBob")
    bob_id = _user_id(app, "dmBob")

    carol_client = app.test_client()
    register(carol_client, username="dmCarol")
    login(carol_client, username="dmCarol")

    sio_alice = socketio.test_client(app, flask_test_client=alice_client)
    sio_bob = socketio.test_client(app, flask_test_client=bob_client)
    sio_carol = socketio.test_client(app, flask_test_client=carol_client)

    sio_alice.emit("join_room", {"target_user_id": bob_id})
    sio_bob.emit("join_room", {"target_user_id": alice_id})
    # carol tries to snoop by (wrongly) targeting bob -- this puts her in dm_<carol>_<bob>,
    # a different room from alice and bob's dm_<alice>_<bob>
    sio_carol.emit("join_room", {"target_user_id": bob_id})

    sio_alice.emit("send_message", {"target_user_id": bob_id, "content": "비밀 메시지"})

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
        lo, hi = sorted((alice_id, bob_id))
        assert saved.room == f"dm_{lo}_{hi}"


def test_dm_self_target_is_ignored(client, db, app):
    register(client, username="selfsock")
    login(client, username="selfsock")
    my_id = _user_id(app, "selfsock")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {"target_user_id": my_id})
    sio_client.emit("send_message", {"target_user_id": my_id, "content": "talking to myself"})

    assert sio_client.get_received() == []
    with app.app_context():
        assert Message.query.filter_by(content="talking to myself").first() is None


def test_dm_target_nonexistent_user_is_ignored(client, db, app):
    register(client, username="ghosttarget")
    login(client, username="ghosttarget")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("send_message", {"target_user_id": 999999, "content": "hello ghost"})

    assert sio_client.get_received() == []
    with app.app_context():
        assert Message.query.filter_by(content="hello ghost").first() is None


def test_empty_message_is_ignored(client, db, app):
    register(client, username="emptysender")
    login(client, username="emptysender")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {})
    sio_client.emit("send_message", {"content": "   "})

    assert sio_client.get_received() == []
    with app.app_context():
        assert Message.query.count() == 0


def test_oversized_message_rejected(client, db, app):
    register(client, username="longsender")
    login(client, username="longsender")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {})
    sio_client.emit("send_message", {"content": "x" * 1001})

    received = sio_client.get_received()
    assert len(received) == 1
    assert received[0]["name"] == "chat_error"
    with app.app_context():
        assert Message.query.count() == 0


def test_rate_limit_blocks_rapid_messages(client, db, app):
    register(client, username="spammer")
    login(client, username="spammer")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {})

    for i in range(8):
        sio_client.emit("send_message", {"content": f"spam {i}"})

    received = sio_client.get_received()
    errors = [e for e in received if e["name"] == "chat_error"]
    messages = [e for e in received if e["name"] == "receive_message"]

    assert len(errors) > 0
    assert len(messages) == 5  # RATE_LIMIT_MAX_MESSAGES


def test_chat_message_history_is_escaped_on_render(client, db, app):
    # the socket payload itself carries raw content (it's just JSON data, not HTML --
    # escaping is the client's job via textContent, already reviewed in code); this
    # test is about the SERVER-rendered history on /products, which must escape it
    register(client, username="xsschatuser")
    login(client, username="xsschatuser")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join_room", {})
    sio_client.emit("send_message", {"content": "<script>alert('xss-chat')</script>"})

    resp = client.get("/products")
    html = resp.get_data(as_text=True)
    assert "<script>alert('xss-chat')</script>" not in html
    assert "&lt;script&gt;alert(&#39;xss-chat&#39;)&lt;/script&gt;" in html
