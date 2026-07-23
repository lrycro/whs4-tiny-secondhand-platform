import os

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

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    from blueprints.auth.routes import auth_bp
    from blueprints.chat.routes import chat_bp
    from blueprints.main.routes import main_bp
    from blueprints.mypage.routes import mypage_bp
    from blueprints.products.routes import products_bp
    from blueprints.report.routes import report_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(mypage_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(report_bp)

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    # allow_unsafe_werkzeug: fine for local dev/demo (SPEC.md's WSL+ngrok setup);
    # a real deployment would run behind eventlet/gevent or a proper WSGI/ASGI server
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
