import pytest
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import BalanceCharge, CHARGE_MAX_AMOUNT, MAX_BALANCE, Transaction, User
from tests.helpers import extract_csrf, login, register


def _set_balance(app, username, amount):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        user.balance = amount
        db.session.commit()


def _get_balance(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().balance


def _transfer(client, receiver_username, amount):
    resp = client.get("/transfer")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/transfer",
        data={"receiver_username": receiver_username, "amount": amount, "csrf_token": token},
        follow_redirects=True,
    )


def _charge(client, amount):
    resp = client.get("/wallet/charge")
    token = extract_csrf(resp.get_data(as_text=True))
    return client.post(
        "/wallet/charge",
        data={"amount": amount, "csrf_token": token},
        follow_redirects=True,
    )


def test_transfer_requires_login(client, db):
    resp = client.get("/transfer", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_transfer_missing_amount_rejected(client, db):
    register(client, username="sender1")  # not logged in yet -- registering doesn't authenticate
    register(client, username="receiver1")
    login(client, username="sender1")

    resp = client.post(
        "/transfer",
        data={
            "receiver_username": "receiver1",
            "amount": "",
            "csrf_token": extract_csrf(client.get("/transfer").get_data(as_text=True)),
        },
        follow_redirects=True,
    )
    assert "송금액을 입력해주세요" in resp.get_data(as_text=True)


def test_transfer_zero_amount_rejected(client, db, app):
    register(client, username="sender2")
    register(client, username="receiver2")
    login(client, username="sender2")
    _set_balance(app, "sender2", 10000)

    resp = _transfer(client, "receiver2", "0")
    assert "송금액은 1원 이상이어야 합니다" in resp.get_data(as_text=True)


def test_transfer_negative_amount_rejected(client, db, app):
    register(client, username="sender3")
    register(client, username="receiver3")
    login(client, username="sender3")
    _set_balance(app, "sender3", 10000)

    resp = _transfer(client, "receiver3", "-500")
    assert "송금액은 1원 이상이어야 합니다" in resp.get_data(as_text=True)


def test_transfer_nonexistent_receiver_rejected(client, db, app):
    register(client, username="sender4")
    login(client, username="sender4")
    _set_balance(app, "sender4", 10000)

    resp = _transfer(client, "ghostuser", "1000")
    assert "존재하지 않는 아이디입니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "sender4") == 10000


def test_transfer_to_self_rejected(client, db, app):
    register(client, username="sender5")
    login(client, username="sender5")
    _set_balance(app, "sender5", 10000)

    resp = _transfer(client, "sender5", "1000")
    assert "본인에게는 송금할 수 없습니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "sender5") == 10000


def test_transfer_insufficient_balance_rejected(client, db, app):
    register(client, username="sender6")
    register(client, username="receiver6")
    login(client, username="sender6")
    _set_balance(app, "sender6", 500)

    resp = _transfer(client, "receiver6", "1000")
    assert "잔액이 부족합니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "sender6") == 500
    assert _get_balance(app, "receiver6") == 0


def test_transfer_success(client, db, app):
    register(client, username="sender7")
    register(client, username="receiver7")
    login(client, username="sender7")
    _set_balance(app, "sender7", 10000)

    resp = _transfer(client, "receiver7", "3000")
    assert "receiver7님에게 3,000원을 송금했습니다" in resp.get_data(as_text=True)

    assert _get_balance(app, "sender7") == 7000
    assert _get_balance(app, "receiver7") == 3000

    with app.app_context():
        tx = Transaction.query.first()
        assert tx is not None
        assert tx.amount == 3000


def test_transfer_prefill_from_query_param(client, db, app):
    register(client, username="sender8")
    register(client, username="receiver8")
    login(client, username="sender8")

    resp = client.get("/transfer?to=receiver8")
    html = resp.get_data(as_text=True)
    assert 'value="receiver8"' in html


def test_balance_check_constraint_rejects_negative(app):
    with app.app_context():
        user = User(username="ckuser")
        user.set_password("Passw0rd!")
        user.balance = -1
        db.session.add(user)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_balance_check_constraint_rejects_over_max(app):
    with app.app_context():
        user = User(username="ckuser3")
        user.set_password("Passw0rd!")
        user.balance = MAX_BALANCE + 1
        db.session.add(user)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_transfer_exceeding_receiver_balance_cap_rejected(client, db, app):
    register(client, username="sender9")
    register(client, username="receiver9")
    login(client, username="sender9")
    _set_balance(app, "sender9", 1000)
    _set_balance(app, "receiver9", MAX_BALANCE - 500)

    resp = _transfer(client, "receiver9", "1000")
    assert f"보유 잔액이 상한({MAX_BALANCE:,}원)을 초과하게 되어 송금할 수 없습니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "sender9") == 1000
    assert _get_balance(app, "receiver9") == MAX_BALANCE - 500


def test_transfer_up_to_receiver_balance_cap_accepted(client, db, app):
    register(client, username="sender10")
    register(client, username="receiver10")
    login(client, username="sender10")
    _set_balance(app, "sender10", 1000)
    _set_balance(app, "receiver10", MAX_BALANCE - 1000)

    resp = _transfer(client, "receiver10", "1000")
    assert "송금했습니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "receiver10") == MAX_BALANCE


def test_charge_requires_login(client, db):
    resp = client.get("/wallet/charge", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_charge_success(client, db, app):
    register(client, username="charger1")
    login(client, username="charger1")
    _set_balance(app, "charger1", 1000)

    resp = _charge(client, "50000")
    assert "50,000원이 충전되었습니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger1") == 51000

    with app.app_context():
        record = BalanceCharge.query.filter_by(user_id=_user_id(app, "charger1")).first()
        assert record is not None
        assert record.amount == 50000


def test_charge_zero_amount_rejected(client, db, app):
    register(client, username="charger2")
    login(client, username="charger2")

    resp = _charge(client, "0")
    assert f"충전 금액은 1원 이상 {CHARGE_MAX_AMOUNT:,}원 이하여야 합니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger2") == 0


def test_charge_negative_amount_rejected(client, db, app):
    register(client, username="charger3")
    login(client, username="charger3")

    resp = _charge(client, "-1000")
    assert f"충전 금액은 1원 이상 {CHARGE_MAX_AMOUNT:,}원 이하여야 합니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger3") == 0


def test_charge_over_max_rejected(client, db, app):
    register(client, username="charger4")
    login(client, username="charger4")

    resp = _charge(client, str(CHARGE_MAX_AMOUNT + 1))
    assert f"충전 금액은 1원 이상 {CHARGE_MAX_AMOUNT:,}원 이하여야 합니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger4") == 0


def test_charge_at_max_boundary_accepted(client, db, app):
    register(client, username="charger5")
    login(client, username="charger5")

    resp = _charge(client, str(CHARGE_MAX_AMOUNT))
    assert f"{CHARGE_MAX_AMOUNT:,}원이 충전되었습니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger5") == CHARGE_MAX_AMOUNT


def test_charge_exceeding_total_balance_cap_rejected(client, db, app):
    register(client, username="charger7")
    login(client, username="charger7")
    _set_balance(app, "charger7", MAX_BALANCE - 500)

    resp = _charge(client, "1000")
    assert f"보유 잔액이 상한({MAX_BALANCE:,}원)을 초과하게 되어 충전할 수 없습니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger7") == MAX_BALANCE - 500


def test_charge_up_to_total_balance_cap_accepted(client, db, app):
    register(client, username="charger8")
    login(client, username="charger8")
    _set_balance(app, "charger8", MAX_BALANCE - 1000)

    resp = _charge(client, "1000")
    assert "충전되었습니다" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger8") == MAX_BALANCE


def test_charge_missing_amount_rejected(client, db, app):
    register(client, username="charger6")
    login(client, username="charger6")

    resp = _charge(client, "")
    assert "충전 금액을 입력해주세요" in resp.get_data(as_text=True)
    assert _get_balance(app, "charger6") == 0


def test_balance_charge_check_constraint_rejects_over_max(app):
    with app.app_context():
        user = User(username="ckuser2")
        user.set_password("Passw0rd!")
        db.session.add(user)
        db.session.commit()

        db.session.add(BalanceCharge(user_id=user.id, amount=CHARGE_MAX_AMOUNT + 1))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def _user_id(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first().id


def test_transactions_requires_login(client, db):
    resp = client.get("/mypage/transactions", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_transactions_shows_own_sent_received_and_charges(client, db, app):
    register(client, username="txsender")
    register(client, username="txreceiver")
    login(client, username="txsender")
    _set_balance(app, "txsender", 10000)

    _transfer(client, "txreceiver", 3000)
    _charge(client, "50000")

    resp = client.get("/mypage/transactions")
    html = resp.get_data(as_text=True)
    assert "txreceiver님에게 송금" in html
    assert "-3,000원" in html
    assert "충전" in html
    assert "+50,000원" in html

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    login(client, username="txreceiver")
    resp2 = client.get("/mypage/transactions")
    html2 = resp2.get_data(as_text=True)
    assert "txsender님에게 받음" in html2
    assert "+3,000원" in html2


def test_transactions_does_not_leak_other_users_history(client, db, app):
    register(client, username="txowner")
    register(client, username="txbystander")
    login(client, username="txowner")
    _set_balance(app, "txowner", 10000)
    _charge(client, "70000")

    logout_token = extract_csrf(client.get("/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": logout_token}, follow_redirects=True)

    login(client, username="txbystander")
    resp = client.get("/mypage/transactions")
    html = resp.get_data(as_text=True)
    assert "70,000원" not in html
    assert "거래 내역이 없습니다" in html


def test_transactions_empty_state(client, db):
    register(client, username="txempty")
    login(client, username="txempty")

    resp = client.get("/mypage/transactions")
    assert "거래 내역이 없습니다" in resp.get_data(as_text=True)
