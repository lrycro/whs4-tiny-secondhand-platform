from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from blueprints.auth.forms import LoginForm, RegistrationForm
from extensions import db
from models import User, UserStatus

auth_bp = Blueprint("auth", __name__)

# same message for "no such user", "wrong password", and "locked out" -- a distinct
# lockout message would leak that a given username exists to someone probing usernames
GENERIC_LOGIN_ERROR = "아이디 또는 비밀번호가 올바르지 않습니다."


def _is_safe_redirect_target(target):
    if not target:
        return False
    parsed = urlparse(target)
    # only allow same-origin relative paths; rejects "http://evil.com", "//evil.com", "javascript:...", etc.
    return not parsed.netloc and not parsed.scheme and target.startswith("/")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user is not None and user.is_locked():
            flash(GENERIC_LOGIN_ERROR, "danger")
        elif user is None or not user.check_password(form.password.data):
            if user is not None:
                user.register_failed_login()
                db.session.commit()
            flash(GENERIC_LOGIN_ERROR, "danger")
        elif user.status == UserStatus.SUSPENDED:
            flash("휴면 처리된 계정입니다. 관리자에게 문의해주세요.", "danger")
        else:
            user.reset_failed_login()
            db.session.commit()
            login_user(user)
            session.permanent = True  # apply PERMANENT_SESSION_LIFETIME idle timeout
            next_page = request.args.get("next")
            if not _is_safe_redirect_target(next_page):
                next_page = url_for("main.index")
            return redirect(next_page)

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("로그아웃 되었습니다.", "info")
    return redirect(url_for("main.index"))
