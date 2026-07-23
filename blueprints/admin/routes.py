from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from extensions import db
from models import AdminActionLog, Product, ProductStatus, Report, ReportTargetType, User, UserStatus

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    # login_required first (redirect to login if not authenticated) THEN the role
    # check (403 if authenticated but not admin) -- both re-verified on the server
    # for every request, never inferred from what the client shows/hides
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin():
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def _log_action(action, target_type, target_id):
    db.session.add(
        AdminActionLog(admin_id=current_user.id, action=action, target_type=target_type, target_id=target_id)
    )


@admin_bp.route("/")
@admin_required
def dashboard():
    counts = {
        "users": User.query.count(),
        "suspended_users": User.query.filter_by(status=UserStatus.SUSPENDED).count(),
        "products": Product.query.count(),
        "blocked_products": Product.query.filter_by(status=ProductStatus.BLOCKED).count(),
        "reports": Report.query.count(),
    }
    return render_template("admin/dashboard.html", counts=counts)


@admin_bp.route("/users")
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_user_status(user_id):
    target = User.query.get_or_404(user_id)
    if target.id == current_user.id:
        # not just hidden client-side -- re-checked here too, so a forged request
        # against your own account is rejected regardless of what the UI shows
        flash("본인의 상태는 변경할 수 없습니다.", "warning")
        return redirect(url_for("admin.users"))

    if target.status == UserStatus.SUSPENDED:
        target.status = UserStatus.ACTIVE
        target.report_count = 0  # clean slate so one new report doesn't instantly re-trigger the block
        _log_action("user_unsuspend", "user", target.id)
        flash(f"{target.username}님의 휴면을 해제했습니다.", "success")
    else:
        target.status = UserStatus.SUSPENDED
        _log_action("user_suspend", "user", target.id)
        flash(f"{target.username}님을 휴면 처리했습니다.", "success")

    db.session.commit()
    return redirect(url_for("admin.users"))


@admin_bp.route("/products")
@admin_required
def products():
    all_products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin/products.html", products=all_products)


@admin_bp.route("/products/<int:product_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_product_status(product_id):
    product = Product.query.get_or_404(product_id)

    if product.status == ProductStatus.BLOCKED:
        product.status = ProductStatus.ACTIVE
        product.report_count = 0
        _log_action("product_unblock", "product", product.id)
        flash(f"'{product.name}' 상품 차단을 해제했습니다.", "success")
    else:
        product.status = ProductStatus.BLOCKED
        _log_action("product_block", "product", product.id)
        flash(f"'{product.name}' 상품을 차단했습니다.", "success")

    db.session.commit()
    return redirect(url_for("admin.products"))


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    _log_action("product_force_delete", "product", product.id)
    db.session.delete(product)
    db.session.commit()
    flash(f"'{name}' 상품을 강제 삭제했습니다.", "info")
    return redirect(url_for("admin.products"))


@admin_bp.route("/reports")
@admin_required
def reports():
    all_reports = Report.query.order_by(Report.created_at.desc()).all()

    enriched = []
    for report in all_reports:
        if report.target_type == ReportTargetType.PRODUCT:
            target = db.session.get(Product, report.target_id)
            target_label = target.name if target else "(삭제된 상품)"
        else:
            target = db.session.get(User, report.target_id)
            target_label = target.username if target else "(삭제된 유저)"
        enriched.append({"report": report, "target_label": target_label})

    return render_template("admin/reports.html", items=enriched)
