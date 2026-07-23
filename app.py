import os

import click
from flask import Flask

from config import Config
from extensions import csrf, db, login_manager, socketio

# Import BEFORE any socketio.init_app() call. @socketio.on(...) decorators register
# directly onto socketio.server if it already exists, or queue into socketio.handlers
# (replayed onto every future server) if it doesn't yet. init_app() always builds a
# brand-new server, discarding direct registrations -- and create_app() runs once per
# test, so importing this after init_app() (as create_app() itself does) means the
# handlers only ever survive for the very first app created in the process.
import blueprints.chat.socket_events  # noqa: F401,E402


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "로그인이 필요합니다."
    login_manager.login_message_category = "warning"

    import models  # noqa: F401  register models with SQLAlchemy metadata before create_all()

    app.jinja_env.filters["kst_time"] = models.format_kst_time
    app.jinja_env.filters["sale_status_label"] = lambda s: models.SALE_STATUS_LABELS.get(s, s.value)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    from blueprints.admin.routes import admin_bp
    from blueprints.auth.routes import auth_bp
    from blueprints.chat.routes import chat_bp
    from blueprints.main.routes import main_bp
    from blueprints.mypage.routes import mypage_bp
    from blueprints.products.routes import products_bp
    from blueprints.report.routes import report_bp
    from blueprints.transfer.routes import transfer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(mypage_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(transfer_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    def create_admin(username, password):
        """Create or promote a user to admin. The ONLY way to get an admin
        account -- the registration form always sets role='user' (never a
        client-controllable field), per SPEC.md's checklist item #30."""
        with app.app_context():
            user = models.User.query.filter_by(username=username).first()
            if user is not None:
                user.role = models.UserRole.ADMIN
                db.session.commit()
                click.echo(f"'{username}' 계정을 admin으로 승격했습니다.")
            else:
                user = models.User(username=username, role=models.UserRole.ADMIN)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                click.echo(f"admin 계정 '{username}'을(를) 생성했습니다.")

    return app


app = create_app()

if __name__ == "__main__":
    # debug defaults to OFF (production-safe): Werkzeug's debug mode shows full stack
    # traces, source code, and a remote code execution console on any unhandled
    # exception -- SPEC.md 2.4 explicitly requires debug=False in deployment. Override
    # to true via .env (FLASK_DEBUG=true) only for local interactive debugging.
    #
    # allow_unsafe_werkzeug is independent of debug -- it's about the WSGI server
    # itself (Werkzeug's dev server, since no eventlet/gevent is installed) not being
    # meant for production, so it stays on regardless for this project's WSL+ngrok
    # demo setup; a real deployment would run behind eventlet/gevent or a proper
    # WSGI/ASGI server instead of this flag.
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(app, debug=debug_mode, allow_unsafe_werkzeug=True)
