from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from extensions import db
from models import ChatThread, Message, Product, User

chat_bp = Blueprint("chat", __name__)

HISTORY_LIMIT = 50


@chat_bp.route("/chat/<int:product_id>/<int:other_user_id>")
@login_required
def dm(product_id, other_user_id):
    if other_user_id == current_user.id:
        flash("본인과는 채팅할 수 없습니다.", "warning")
        return redirect(url_for("products.product_list"))

    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)

    other_user = db.session.get(User, other_user_id)
    if other_user is None:
        abort(404)

    # a product's chat threads only ever exist between ITS seller and one buyer --
    # never between two unrelated users, regardless of what the client requests
    if current_user.id == product.seller_id:
        buyer_id = other_user_id
    elif other_user_id == product.seller_id:
        buyer_id = current_user.id
    else:
        abort(403)

    thread = ChatThread.query.filter_by(product_id=product_id, buyer_id=buyer_id).first()
    if thread is None:
        thread = ChatThread(product_id=product_id, buyer_id=buyer_id)
        db.session.add(thread)
        db.session.commit()

    history = (
        Message.query.filter_by(thread_id=thread.id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    history.reverse()

    return render_template(
        "chat/dm.html", product=product, other_user=other_user, thread=thread, history=history
    )


@chat_bp.route("/chat")
@login_required
def chat_list():
    my_threads = (
        ChatThread.query.join(Product, ChatThread.product_id == Product.id)
        .filter(db.or_(ChatThread.buyer_id == current_user.id, Product.seller_id == current_user.id))
        .order_by(ChatThread.created_at.desc())
        .all()
    )

    items = []
    for thread in my_threads:
        other_id = thread.other_party_id(current_user.id)
        other_user = db.session.get(User, other_id)
        last_message = (
            Message.query.filter_by(thread_id=thread.id).order_by(Message.created_at.desc()).first()
        )
        items.append({"thread": thread, "other_user": other_user, "last_message": last_message})

    return render_template("chat/list.html", items=items)
