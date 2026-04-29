import os

from dotenv import load_dotenv
from flask import Flask

load_dotenv()


def create_app(db_path: str | None = None) -> Flask:
    """
    Flask application factory.

    Args:
        db_path: Path to the SQLite database. Falls back to the DB_PATH
                 environment variable, then to 'conan.db'.
    """
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    app.config["DB_PATH"] = db_path or os.getenv("DB_PATH", "conan.db")
    app.config["DEBUG"] = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Register teardown so every request closes its DB connection cleanly
    from app.db import close_db
    app.teardown_appcontext(close_db)

    # Register blueprints
    from app.routes.collection import bp as collection_bp
    from app.routes.api import bp as api_bp
    from app.routes.ai import bp as ai_bp

    app.register_blueprint(collection_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(ai_bp)

    return app
