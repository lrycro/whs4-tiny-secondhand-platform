from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from blueprints.transfer.forms import ChargeForm, TransferForm
from extensions import db
from models import BalanceCharge, Transaction, User

transfer_bp = Blueprint("transfer", __name__)


@transfer_bp.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    form = TransferForm()
    if request.method == "GET":
        prefill = request.args.get("to")
        if prefill:
            form.receiver_username.data = prefill

    if form.validate_on_submit():
        receiver = User.query.filter_by(username=form.receiver_username.data).first()
        amount = form.amount.data

        if receiver is None:
            form.receiver_username.errors.append("존재하지 않는 아이디입니다.")
        elif receiver.id == current_user.id:
            form.receiver_username.errors.append("본인에게는 송금할 수 없습니다.")
        elif current_user.balance < amount:
            form.amount.errors.append("잔액이 부족합니다.")
        else:
            try:
                current_user.balance -= amount
                receiver.balance += amount
                db.session.add(
                    Transaction(sender_id=current_user.id, receiver_id=receiver.id, amount=amount)
                )
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                flash("송금 처리 중 오류가 발생했습니다. 다시 시도해주세요.", "danger")
                return render_template("transfer/form.html", form=form, balance=current_user.balance)

            flash(f"{receiver.username}님에게 {amount:,}원을 송금했습니다.", "success")
            return redirect(url_for("transfer.transfer"))

    return render_template("transfer/form.html", form=form, balance=current_user.balance)


@transfer_bp.route("/wallet/charge", methods=["GET", "POST"])
@login_required
def charge():
    form = ChargeForm()

    if form.validate_on_submit():
        amount = form.amount.data
        try:
            current_user.balance += amount
            db.session.add(BalanceCharge(user_id=current_user.id, amount=amount))
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash("충전 처리 중 오류가 발생했습니다. 다시 시도해주세요.", "danger")
            return render_template("transfer/charge.html", form=form, balance=current_user.balance)

        flash(f"{amount:,}원이 충전되었습니다.", "success")
        return redirect(url_for("transfer.charge"))

    return render_template("transfer/charge.html", form=form, balance=current_user.balance)
