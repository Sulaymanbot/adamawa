"""Application factory for the Adamawa LG Online Voting prototype.

SIMULATED ACADEMIC PROTOTYPE – NOT AN OFFICIAL ELECTION PLATFORM.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Load backend/.env before config classes read os.environ (tests opt out).
if not os.environ.get("ADV_SKIP_DOTENV"):
    load_dotenv(BACKEND_DIR / ".env")

from app.config import CONFIGS, validate_config
from app.errors import register_error_handlers
from app.extensions import csrf, db, limiter, migrate
from app.logging_setup import configure_logging
from app.security.headers import init_security
from app.security.sessions import load_current_user


def create_app(env: str | None = None, overrides: dict | None = None) -> Flask:
    env = env or os.environ.get("FLASK_ENV", "development")
    if env not in CONFIGS:
        raise RuntimeError(f"Unknown FLASK_ENV '{env}'. Use development, production or testing.")
    config_cls = CONFIGS[env]

    # Presentation tier: app/templates (HTML) and app/static (CSS, JS, fonts, vendored libs).
    app = Flask(__name__)
    app.config.from_object(config_cls)
    app.config.update(config_cls.load_secrets())
    if overrides:
        app.config.update(overrides)
    validate_config(app.config)

    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True, compare_type=True)
    csrf.init_app(app)

    # Order matters: request id + current user must exist before the limiter
    # computes per-user keys and before error handlers write audit records.
    init_security(app)
    app.before_request(load_current_user)
    limiter.init_app(app)
    # Start each app instance with empty in-memory counters (no-op for other storages).
    with contextlib.suppress(Exception):
        limiter.reset()

    register_error_handlers(app)

    from app import models  # noqa: F401  (register models with SQLAlchemy)
    from app.api import api_v1
    from app.web import web

    app.register_blueprint(api_v1)
    app.register_blueprint(web)

    from app.cli import register_cli

    register_cli(app)

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "app_name": app.config["APP_NAME"],
            "demo_mode": app.config["DEMO_MODE"],
            "otp_enabled": app.config["OTP_ENABLED"],
        }

    return app
