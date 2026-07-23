from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from blueprints.mypage.forms import BioForm, ChangePasswordForm
from extensions import db
from models import BalanceCharge, Product, ProductStatus, Transaction, User

mypage_bp = Blueprint("mypage", __name__)


@mypage_bp.route("/mypage", methods=["GET", "POST"])
@login_required
def mypage():
    # both forms always target current_user directly (never a client-supplied id),
    # so there is no IDOR surface to re-check ownership against here
    bio_form = BioForm(obj=current_user)
    password_form = ChangePasswordForm()

    if "submit_bio" in request.form and bio_form.validate_on_submit():
        current_user.bio = bio_form.bio.data
        db.session.commit()
        flash("소개글이 수정되었습니다.", "success")
        return redirect(url_for("mypage.mypage"))

    if "submit_password" in request.form and password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            flash("현재 비밀번호가 일치하지 않습니다.", "danger")
        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash("비밀번호가 변경되었습니다.", "success")
            return redirect(url_for("mypage.mypage"))

    my_products = (
        Product.query.filter_by(seller_id=current_user.id).order_by(Product.created_at.desc()).all()
    )
    return render_template(
        "mypage.html", bio_form=bio_form, password_form=password_form, my_products=my_products
    )


@mypage_bp.route("/profile/<int:user_id>")
@login_required
def profile(user_id):
    # SPEC.md U3/F4: 타인 프로필은 "최소 정보만" 노출 -- balance, role, status,
    # report_count, 이메일 등 민감/내부 필드는 절대 템플릿에 넘기지 않는다.
    profile_user = User.query.get_or_404(user_id)
    products = (
        Product.query.filter_by(seller_id=profile_user.id, status=ProductStatus.ACTIVE)
        .order_by(Product.created_at.desc())
        .all()
    )
    return render_template("profile.html", profile_user=profile_user, products=products)


@mypage_bp.route("/mypage/transactions")
@login_required
def transactions():
    # 읽기 전용 조회. 항상 current_user.id로만 필터링하므로 클라이언트가
    # 다른 유저의 거래 내역을 볼 수 있는 IDOR 경로가 없다.
    transfers = (
        Transaction.query.filter(
            db.or_(Transaction.sender_id == current_user.id, Transaction.receiver_id == current_user.id)
        )
        .order_by(Transaction.created_at.desc())
        .all()
    )
    charges = (
        BalanceCharge.query.filter_by(user_id=current_user.id)
        .order_by(BalanceCharge.created_at.desc())
        .all()
    )

    events = []
    for tx in transfers:
        direction = "sent" if tx.sender_id == current_user.id else "received"
        counterpart_id = tx.receiver_id if direction == "sent" else tx.sender_id
        events.append(
            {
                "type": "transfer",
                "direction": direction,
                "amount": tx.amount,
                "counterpart": db.session.get(User, counterpart_id),
                "created_at": tx.created_at,
            }
        )
    for charge in charges:
        events.append(
            {
                "type": "charge",
                "direction": None,
                "amount": charge.amount,
                "counterpart": None,
                "created_at": charge.created_at,
            }
        )
    events.sort(key=lambda e: e["created_at"], reverse=True)

    return render_template("transactions.html", events=events)
