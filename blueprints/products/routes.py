import os
import uuid

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from blueprints.products.forms import ProductCreateForm, ProductForm
from extensions import db
from models import GlobalMessage, Product, ProductStatus

products_bp = Blueprint("products", __name__)

SEARCH_QUERY_MAX_LENGTH = 200
CHAT_HISTORY_LIMIT = 50


def _recent_global_messages():
    history = (
        GlobalMessage.query.order_by(GlobalMessage.created_at.desc()).limit(CHAT_HISTORY_LIMIT).all()
    )
    history.reverse()
    return history


def _like_pattern(term):
    # escape LIKE wildcards in user input so e.g. searching "50%" doesn't match everything;
    # SQLAlchemy still parameter-binds the value itself, so this is a correctness fix, not
    # an injection fix -- the ORM already prevents SQL injection here.
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _save_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    # random filename: never trust/store the client-supplied name (path traversal, collisions)
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = current_app.config["PRODUCT_UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, filename))
    return filename


@products_bp.route("/products")
@login_required
def product_list():
    products = (
        Product.query.filter_by(status=ProductStatus.ACTIVE).order_by(Product.created_at.desc()).all()
    )
    return render_template(
        "products/list.html", products=products, search_query="", chat_history=_recent_global_messages()
    )


@products_bp.route("/products/search")
@login_required
def product_search():
    raw_query = request.args.get("q", "").strip()[:SEARCH_QUERY_MAX_LENGTH]

    query = Product.query.filter_by(status=ProductStatus.ACTIVE)
    if raw_query:
        pattern = _like_pattern(raw_query)
        query = query.filter(
            db.or_(
                Product.name.ilike(pattern, escape="\\"),
                Product.description.ilike(pattern, escape="\\"),
            )
        )
    products = query.order_by(Product.created_at.desc()).all()
    return render_template(
        "products/list.html",
        products=products,
        search_query=raw_query,
        chat_history=_recent_global_messages(),
    )


@products_bp.route("/products/new", methods=["GET", "POST"])
@login_required
def product_new():
    form = ProductCreateForm()
    if form.validate_on_submit():
        product = Product(
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            seller_id=current_user.id,
            image_filename=_save_photo(form.photo.data),
        )
        db.session.add(product)
        db.session.commit()
        flash("상품이 등록되었습니다.", "success")
        return redirect(url_for("products.product_detail", product_id=product.id))
    return render_template("products/form.html", form=form, mode="new")


@products_bp.route("/products/<int:product_id>")
@login_required
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("products/detail.html", product=product)


@products_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        abort(403)

    form = ProductForm(obj=product)
    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        new_filename = _save_photo(form.photo.data)
        if new_filename:
            product.image_filename = new_filename
        db.session.commit()
        flash("상품 정보가 수정되었습니다.", "success")
        return redirect(url_for("products.product_detail", product_id=product.id))
    return render_template("products/form.html", form=form, mode="edit", product=product)


@products_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        abort(403)

    db.session.delete(product)
    db.session.commit()
    flash("상품이 삭제되었습니다.", "info")
    return redirect(url_for("mypage.mypage"))
