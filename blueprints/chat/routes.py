from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from blueprints.chat.socket_events import dm_room_name
from extensions import db
from models import Message, User

chat_bp = Blueprint("chat", __name__)

HISTORY_LIMIT = 50


@chat_bp.route("/chat/<int:user_id>")
@login_required
def dm(user_id):
    if user_id == current_user.id:
        flash("본인과는 채팅할 수 없습니다.", "warning")
        return redirect(url_for("products.product_list"))

    other_user = db.session.get(User, user_id)
    if other_user is None:
        abort(404)

    room = dm_room_name(current_user.id, user_id)
    history = (
        Message.query.filter_by(room=room).order_by(Message.created_at.desc()).limit(HISTORY_LIMIT).all()
    )
    history.reverse()

    return render_template("chat/dm.html", other_user=other_user, history=history)
