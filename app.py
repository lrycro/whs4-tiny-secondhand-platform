import os

from flask import Flask

from config import Config
from extensions import csrf, db, login_manager, socketio


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)

    # auth blueprint (login/register) lands in step 2 of SPEC.md 3
    login_manager.login_view = "auth.login"

    import models  # noqa: F401  register models with SQLAlchemy metadata before create_all()

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    socketio.run(app, debug=True)
