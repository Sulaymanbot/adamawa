"""Environment-based configuration.

All secrets come from environment variables (loaded from backend/.env in
development). Nothing secret is hardcoded here.
"""

from __future__ import annotations

import base64
import os
import secrets
from datetime import timedelta


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value not in (None, "") else default


def _list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalize_database_url(url: str | None) -> str | None:
    """Accept plain mysql:// URLs from hosting dashboards and use the PyMySQL driver."""
    if url and url.startswith("mysql://"):
        return "mysql+pymysql://" + url[len("mysql://") :]
    return url


def engine_options() -> dict:
    """SQLAlchemy engine options, including TLS for cloud MySQL.

    DB_SSL_CA       path to the provider's CA certificate, or
    DB_SSL_CA_PEM   the certificate text itself (handy for hosting env vars).
    DB_SSL_VERIFY_IDENTITY=false only for self-signed local servers.
    """
    options: dict = {"pool_pre_ping": True, "pool_recycle": 280}
    ca_path = os.environ.get("DB_SSL_CA")
    pem = os.environ.get("DB_SSL_CA_PEM")
    if pem and not ca_path:
        import hashlib
        import tempfile

        pem = pem.replace("\\n", "\n").strip() + "\n"
        target = os.path.join(tempfile.gettempdir(), f"db-ca-{hashlib.sha256(pem.encode()).hexdigest()[:12]}.pem")
        with open(target, "w") as fh:
            fh.write(pem)
        ca_path = target
    if ca_path:
        options["connect_args"] = {"ssl": {"ca": ca_path, "check_hostname": _bool("DB_SSL_VERIFY_IDENTITY", True)}}
    return options


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


class BaseConfig:
    APP_NAME = "Adamawa LG Online Voting (Simulated Prototype)"
    APP_ENV = "base"

    MAX_CONTENT_LENGTH = 64 * 1024  # requests are small JSON documents

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Sessions: signed cookie that only carries an opaque session id; the
    # session itself lives in the user_sessions table so it can be revoked.
    SESSION_COOKIE_NAME = "adv_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_IDLE_MINUTES = _int("SESSION_IDLE_MINUTES", 30)
    SESSION_ABSOLUTE_HOURS = _int("SESSION_ABSOLUTE_HOURS", 8)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=SESSION_ABSOLUTE_HOURS)

    # CSRF (Flask-WTF). Token is sent by fetch() in the X-CSRFToken header.
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # bound to the session instead
    WTF_CSRF_HEADERS = ["X-CSRFToken", "X-CSRF-Token"]

    # Only these origins receive CORS headers. The bundled HTML UI is served
    # from the same origin and does not need CORS at all.
    CORS_ORIGINS = _list("CORS_ORIGINS", "")

    # Rate limiting (Flask-Limiter)
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    LOGIN_RATE_LIMIT = os.environ.get("LOGIN_RATE_LIMIT", "10 per minute;50 per hour")
    OTP_RATE_LIMIT = os.environ.get("OTP_RATE_LIMIT", "5 per minute")
    VOTE_RATE_LIMIT = os.environ.get("VOTE_RATE_LIMIT", "5 per minute")
    REGISTER_RATE_LIMIT = os.environ.get("REGISTER_RATE_LIMIT", "5 per minute;30 per hour")

    # OTP second factor (mock provider only in this prototype)
    OTP_ENABLED = _bool("OTP_ENABLED", False)
    OTP_TTL_SECONDS = _int("OTP_TTL_SECONDS", 300)
    OTP_MAX_ATTEMPTS = _int("OTP_MAX_ATTEMPTS", 5)

    # Demo / prototype switches
    DEMO_MODE = _bool("DEMO_MODE", True)
    DEMO_ADMIN_OVERRIDE = _bool("DEMO_ADMIN_OVERRIDE", False)

    # Races with fewer valid votes than this have their per-candidate counts
    # withheld in published results to reduce inference of individual ballots.
    RESULTS_MIN_RACE_VOTES = _int("RESULTS_MIN_RACE_VOTES", 3)

    # Audit IP handling: "hash" (keyed hash) or "none".
    AUDIT_IP_MODE = os.environ.get("AUDIT_IP_MODE", "hash")

    # Add HSTS header (only meaningful behind HTTPS).
    ENABLE_HSTS = _bool("ENABLE_HSTS", False)

    # Behind a hosting proxy (PythonAnywhere, nginx…): trust X-Forwarded-* from
    # exactly one hop so request.scheme is https and remote_addr is the client.
    TRUST_PROXY = _bool("TRUST_PROXY", False)

    # Allow `flask seed-test-users` outside development (school demo hosting).
    ALLOW_DEMO_SEED = _bool("ALLOW_DEMO_SEED", False)

    BCRYPT_ROUNDS = _int("BCRYPT_ROUNDS", 12)

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_JSON = _bool("LOG_JSON", True)

    SECRET_KEY: str | None = None
    VOTE_ENCRYPTION_KEY: str | None = None
    IDENTIFIER_PEPPER: str | None = None
    SQLALCHEMY_DATABASE_URI: str | None = None

    @classmethod
    def load_secrets(cls) -> dict:
        return {
            "SECRET_KEY": os.environ.get("SECRET_KEY"),
            "VOTE_ENCRYPTION_KEY": os.environ.get("VOTE_ENCRYPTION_KEY"),
            "IDENTIFIER_PEPPER": os.environ.get("IDENTIFIER_PEPPER"),
            "SQLALCHEMY_DATABASE_URI": normalize_database_url(os.environ.get("DATABASE_URL")),
            "SQLALCHEMY_ENGINE_OPTIONS": engine_options(),
        }


class DevelopmentConfig(BaseConfig):
    APP_ENV = "development"
    LOG_JSON = _bool("LOG_JSON", False)


class ProductionConfig(BaseConfig):
    """Production-like settings (HTTPS hosting). This prototype is NOT approved for real elections."""

    LOG_JSON = True

    APP_ENV = "production"
    SESSION_COOKIE_SECURE = True
    ENABLE_HSTS = True
    DEMO_ADMIN_OVERRIDE = False


class TestingConfig(BaseConfig):
    APP_ENV = "testing"
    TESTING = True
    RATELIMIT_ENABLED = False
    OTP_ENABLED = False
    DEMO_ADMIN_OVERRIDE = False
    LOG_JSON = False
    RESULTS_MIN_RACE_VOTES = 3
    BCRYPT_ROUNDS = 4  # fast hashing for the test suite only

    @classmethod
    def load_secrets(cls) -> dict:
        return {
            "SECRET_KEY": secrets.token_hex(32),
            "VOTE_ENCRYPTION_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
            "IDENTIFIER_PEPPER": secrets.token_hex(32),
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        }


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def validate_config(config: dict) -> None:
    """Fail fast when required secrets are missing or malformed."""
    missing = [
        key
        for key in ("SECRET_KEY", "VOTE_ENCRYPTION_KEY", "IDENTIFIER_PEPPER", "SQLALCHEMY_DATABASE_URI")
        if not config.get(key)
    ]
    if missing:
        raise ConfigError(
            "Missing required configuration: " + ", ".join(missing) + ". Copy backend/.env.example to backend/.env and run "
            "`python scripts/init_env.py` to generate local secrets."
        )
    try:
        key = base64.b64decode(config["VOTE_ENCRYPTION_KEY"], validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError("VOTE_ENCRYPTION_KEY must be base64-encoded") from exc
    if len(key) != 32:
        raise ConfigError("VOTE_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256)")
    if len(config["SECRET_KEY"]) < 32:
        raise ConfigError("SECRET_KEY must be at least 32 characters")
    if config.get("APP_ENV") == "production" and config.get("DEMO_ADMIN_OVERRIDE"):
        raise ConfigError("DEMO_ADMIN_OVERRIDE cannot be enabled in production")
