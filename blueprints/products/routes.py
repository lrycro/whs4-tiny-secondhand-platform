import os
import uuid

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from blueprints.products.forms import ProductCreateForm, ProductForm, PurchaseForm, SaleStatusForm
from extensions import db
from models import (
    MAX_BALANCE,
    ChatThread,
    GlobalMessage,
    Product,
    ProductSaleStatus,
    ProductStatus,
    Transaction,
    User,
)

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
    sale_status_form = None
    purchase_form = None
    if current_user.id == product.seller_id:
        sale_status_form = SaleStatusForm(sale_status=product.sale_status.value)
    elif product.sale_status == ProductSaleStatus.ON_SALE:
        purchase_form = PurchaseForm()

    # 구매자 정보는 실제 당사자(판매자/구매자)에게만 노출 -- 프로필과 동일한 원칙으로
    # 제3자에게 "누가 샀는지" 노출하지 않는다
    show_buyer = product.buyer_id is not None and current_user.id in (
        product.seller_id,
        product.buyer_id,
    )

    return render_template(
        "products/detail.html",
        product=product,
        sale_status_form=sale_status_form,
        purchase_form=purchase_form,
        show_buyer=show_buyer,
    )


@products_bp.route("/products/<int:product_id>/purchase", methods=["POST"])
@login_required
def product_purchase(product_id):
    product = Product.query.get_or_404(product_id)

    # 서버측 재검증 (IDOR) -- "구매하기" 버튼이 화면에 안 보이는 것만으로는 부족하다,
    # 클라이언트가 폼을 위조해 직접 POST해도 여기서 막혀야 한다
    if product.seller_id == current_user.id:
        abort(403)

    form = PurchaseForm()
    if not form.validate_on_submit():
        flash("잘못된 요청입니다.", "danger")
        return redirect(url_for("products.product_detail", product_id=product_id))

    if current_user.balance < product.price:
        flash("잔액이 부족합니다.", "danger")
        return redirect(url_for("products.product_detail", product_id=product_id))

    try:
        # 동시 구매 방지의 핵심: "아직 판매중일 때만" 상태를 바꾸는 단일 원자적
        # UPDATE. 두 요청이 거의 동시에 도착해도 DB가 이 UPDATE들을 직렬화하므로
        # 먼저 반영되는 쪽만 영향받은 row가 1개이고, 나머지는 0개가 된다 -- 조회 후
        # 판단(check-then-act)이 아니라 조건부 UPDATE 자체가 원자적 잠금 역할을 한다.
        result = db.session.execute(
            update(Product)
            .where(Product.id == product_id, Product.sale_status == ProductSaleStatus.ON_SALE)
            .values(sale_status=ProductSaleStatus.SOLD, buyer_id=current_user.id)
        )

        if result.rowcount == 0:
            db.session.rollback()
            current_status = db.session.get(Product, product_id).sale_status
            if current_status == ProductSaleStatus.RESERVED:
                flash("예약 중인 상품이라 구매할 수 없습니다.", "danger")
            else:
                flash("이미 판매된 상품입니다.", "danger")
            return redirect(url_for("products.product_detail", product_id=product_id))

        seller = db.session.get(User, product.seller_id)

        # 잔액/상한 재검증(요청 시작 시점 이후 다른 거래로 바뀌었을 수 있음) --
        # 송금 라우트와 동일한 이중 방어 원칙
        if current_user.balance < product.price:
            db.session.rollback()
            flash("잔액이 부족합니다.", "danger")
            return redirect(url_for("products.product_detail", product_id=product_id))
        if seller.balance + product.price > MAX_BALANCE:
            db.session.rollback()
            flash("판매자의 보유 잔액이 상한을 초과하게 되어 구매할 수 없습니다.", "danger")
            return redirect(url_for("products.product_detail", product_id=product_id))

        current_user.balance -= product.price
        seller.balance += product.price
        db.session.add(
            Transaction(
                sender_id=current_user.id,
                receiver_id=seller.id,
                amount=product.price,
                product_id=product.id,
            )
        )

        # 채팅 스레드 자동 생성/연결: 이 상품에 대해 이미 문의하며 대화한 스레드가
        # 있으면 재사용, 없으면 새로 만든다 (ChatThread가 이미 product_id+buyer_id
        # 기준이라 자연스럽게 맞물림)
        thread = ChatThread.query.filter_by(product_id=product.id, buyer_id=current_user.id).first()
        if thread is None:
            db.session.add(ChatThread(product_id=product.id, buyer_id=current_user.id))

        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("구매 처리 중 오류가 발생했습니다. 다시 시도해주세요.", "danger")
        return redirect(url_for("products.product_detail", product_id=product_id))

    flash("구매가 완료되었습니다.", "success")
    return redirect(url_for("products.product_detail", product_id=product_id))


@products_bp.route("/products/<int:product_id>/status", methods=["POST"])
@login_required
def product_status(product_id):
    product = Product.query.get_or_404(product_id)
    # ownership re-verified server-side regardless of what the client's UI showed (IDOR)
    if product.seller_id != current_user.id:
        abort(403)

    form = SaleStatusForm()
    if form.validate_on_submit():
        product.sale_status = ProductSaleStatus(form.sale_status.data)
        db.session.commit()
        flash("판매 상태가 변경되었습니다.", "success")
    else:
        flash("판매 상태를 변경하지 못했습니다.", "danger")
    return redirect(url_for("products.product_detail", product_id=product.id))


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
