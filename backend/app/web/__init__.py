"""Server-rendered HTML pages (presentation tier).

Pages render a shell; data is loaded from /api/v1 by vanilla JS modules.
Access is enforced here on the server before any template is rendered.
"""

from flask import Blueprint, g, redirect, render_template, request, url_for

from app.security.authz import has_permission, page_auth

web = Blueprint("web", __name__)


def _landing() -> str:
    user = g.get("user")
    if user is None:
        return url_for("web.index")
    return url_for("web.admin_dashboard") if has_permission(user, "admin.dashboard") else url_for("web.dashboard")


def _safe_next(default: str) -> str:
    nxt = request.args.get("next", "")
    # Only allow local absolute paths to avoid open redirects.
    if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
        return nxt
    return default


@web.get("/")
def index():
    return render_template("index.html")


@web.get("/healthz")
def healthz():
    """Liveness/readiness probe for the hosting platform (checks the database too)."""
    from app.extensions import db

    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return {"status": "error", "database": "unreachable"}, 503
    return {"status": "ok"}


@web.get("/help")
def help_page():
    return render_template("help.html")


@web.get("/register")
def register():
    if g.get("user"):
        return redirect(_landing())
    return render_template("register.html")


@web.get("/login")
def login():
    if g.get("user"):
        return redirect(_landing())
    return render_template("login.html", portal="voter", next_url=_safe_next(""))


@web.get("/admin/login")
def admin_login():
    if g.get("user"):
        return redirect(_landing())
    return render_template("login.html", portal="admin", next_url=_safe_next(""))


@web.get("/login/otp")
def login_otp():
    return render_template("otp.html", next_url=_safe_next(""))


@web.get("/results")
def results_list():
    return render_template("results_list.html")


@web.get("/results/<int:election_id>")
def results_detail(election_id: int):
    return render_template("results.html", election_id=election_id)


@web.get("/receipt-check")
def receipt_check():
    return render_template("receipt_check.html")


# ---------------------------------------------------------------- voter pages


@web.get("/dashboard")
@page_auth("voter.self")
def dashboard():
    return render_template("voter/dashboard.html")


@web.get("/elections/<int:election_id>")
@page_auth("ballot.cast")
def ballot(election_id: int):
    return render_template("voter/ballot.html", election_id=election_id)


@web.get("/elections/<int:election_id>/receipt")
@page_auth("voter.self")
def receipt(election_id: int):
    return render_template("voter/receipt.html", election_id=election_id)


# ---------------------------------------------------------------- admin pages


@web.get("/admin")
@page_auth("admin.dashboard", login_endpoint="web.admin_login")
def admin_dashboard():
    return render_template("admin/dashboard.html")


@web.get("/admin/voters")
@page_auth("voters.read", login_endpoint="web.admin_login")
def admin_voters():
    return render_template("admin/voters.html")


@web.get("/admin/elections")
@page_auth("elections.manage", login_endpoint="web.admin_login")
def admin_elections():
    return render_template("admin/elections.html")


@web.get("/admin/elections/<int:election_id>")
@page_auth("elections.manage", login_endpoint="web.admin_login")
def admin_election_detail(election_id: int):
    return render_template("admin/election_detail.html", election_id=election_id)


@web.get("/admin/audit-logs")
@page_auth("audit.read", login_endpoint="web.admin_login")
def admin_audit():
    return render_template("admin/audit.html")
