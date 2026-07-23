from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from blueprints.report.forms import ReportForm
from extensions import db
from models import Product, Report, ReportTargetType, User

report_bp = Blueprint("report", __name__)


def _get_target(target_type, target_id):
    if target_type == "product":
        return db.session.get(Product, target_id)
    if target_type == "user":
        return db.session.get(User, target_id)
    return None


@report_bp.route("/report", methods=["GET", "POST"])
@login_required
def report():
    target_type = request.values.get("target_type")
    target_id = request.values.get("target_id", type=int)

    if target_type not in ("user", "product") or not target_id:
        flash("신고 대상이 올바르지 않습니다.", "danger")
        return redirect(url_for("products.product_list"))

    target = _get_target(target_type, target_id)
    if target is None:
        abort(404)

    # never let someone report their own product/account -- also keeps the
    # dm_<uid1>_<uid2>-style "no self-target" invariant consistent across features
    if target_type == "product" and target.seller_id == current_user.id:
        flash("본인의 상품은 신고할 수 없습니다.", "warning")
        return redirect(url_for("products.product_detail", product_id=target.id))
    if target_type == "user" and target.id == current_user.id:
        flash("본인을 신고할 수 없습니다.", "warning")
        return redirect(url_for("products.product_list"))

    form = ReportForm(target_type=target_type, target_id=target_id)

    if form.validate_on_submit():
        existing = Report.query.filter_by(
            reporter_id=current_user.id,
            target_type=ReportTargetType(target_type),
            target_id=target_id,
        ).first()
        if existing is not None:
            flash("이미 신고한 대상입니다.", "warning")
            return redirect(url_for("products.product_list"))

        report_row = Report(
            reporter_id=current_user.id,
            target_type=ReportTargetType(target_type),
            target_id=target_id,
            reason=form.reason.data,
        )
        db.session.add(report_row)
        target.register_report()
        db.session.commit()

        flash("신고가 접수되었습니다.", "success")
        return redirect(url_for("products.product_list"))

    return render_template("report/form.html", form=form, target_type=target_type, target=target)
