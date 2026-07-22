from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from blueprints.mypage.forms import BioForm, ChangePasswordForm
from extensions import db
from models import Product

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
