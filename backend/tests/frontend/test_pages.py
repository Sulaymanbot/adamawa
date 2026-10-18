"""Server-rendered page tests: rendering, access control, accessibility basics.

JavaScript behaviour (validation, ballot review, modal) is covered by the
Playwright end-to-end test in tests/e2e.
"""

import re
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
STATIC = APP_DIR / "static"
TEMPLATES = APP_DIR / "templates"

PUBLIC = ["/", "/help", "/register", "/login", "/admin/login", "/results", "/results/1", "/receipt-check"]
VOTER_PAGES = ["/dashboard", "/elections/1", "/elections/1/receipt"]
ADMIN_PAGES = ["/admin", "/admin/voters", "/admin/elections", "/admin/elections/1", "/admin/audit-logs"]
BRAND = "Adamawa Vote"


@pytest.mark.parametrize("path", PUBLIC)
def test_public_pages_render_with_banner(client, world, path):
    resp = client.get(path)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert BRAND in html
    assert '<meta name="csrf-token"' in html
    assert 'href="#main"' in html, "skip link"


@pytest.mark.parametrize("path", VOTER_PAGES)
def test_voter_pages_redirect_to_login(client, world, path):
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("/login?next=")


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_pages_redirect_to_admin_login(client, world, path):
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("/admin/login?next=")


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_pages_forbidden_for_voter(voter_client, world, path):
    resp = voter_client("yn1").get(path)
    assert resp.status_code == 403
    assert "Access denied" in resp.get_data(as_text=True)


@pytest.mark.parametrize("path", ["/elections/1", "/dashboard"])
def test_voter_pages_forbidden_for_admin(admin_client, world, path):
    assert admin_client.get(path).status_code == 403


@pytest.mark.parametrize("path", VOTER_PAGES)
def test_voter_pages_render_for_voter(voter_client, world, path):
    assert voter_client("yn1").get(path).status_code == 200


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_pages_render_for_admin(admin_client, world, path):
    html = admin_client.get(path).get_data(as_text=True)
    assert BRAND in html and "Sign out" in html


def test_navigation_depends_on_role(admin_client, voter_client, world):
    admin_html = admin_client.get("/admin").get_data(as_text=True)
    assert 'href="/admin/voters"' in admin_html and 'href="/admin/audit-logs"' in admin_html
    voter_html = voter_client("yn1").get("/dashboard").get_data(as_text=True)
    assert 'href="/admin' not in voter_html.replace('href="/admin/login"', "")
    assert "My dashboard" in voter_html


def test_logged_in_users_skip_login_page(voter_client, admin_client, world):
    assert voter_client("yn1").get("/login").headers["Location"] == "/dashboard"
    assert admin_client.get("/admin/login").headers["Location"] == "/admin"


def test_404_page(client, world):
    resp = client.get("/no-such-page")
    assert resp.status_code == 404 and "Page not found" in resp.get_data(as_text=True)


def test_api_404_is_json(client, world):
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404 and resp.get_json()["error"]["code"] == "not_found"


def test_ballot_has_no_preselected_choice(voter_client, world):
    html = voter_client("yn1").get(f"/elections/{world['election'].id}").get_data(as_text=True)
    assert "checked" not in html
    assert 'role="radiogroup"' in html and "<fieldset>" in html and "<legend" in html
    js = (STATIC / "js" / "pages" / "ballot.js").read_text()
    assert not re.search(r"\.checked\s*=\s*true|setAttribute\(\s*['\"]checked", js), "ballot JS must never preselect"
    assert "localStorage" not in js and "sessionStorage" not in js, "choice must not be persisted client-side"


def test_ballot_has_review_and_confirmation_modal(voter_client, world):
    html = voter_client("yn1").get(f"/elections/{world['election'].id}").get_data(as_text=True)
    assert 'id="review-step"' in html
    assert 'id="confirm-modal"' in html and "cannot be undone" in html
    assert 'aria-labelledby="confirm-title"' in html


def test_results_page_includes_table_and_chart_assets(client, world):
    html = client.get("/results/1").get_data(as_text=True)
    assert "vendor/chart.umd.min.js" in html and "SIMULATED RESULTS" in html


def test_no_inline_scripts_or_external_assets():
    """Every page must work under CSP default-src 'self'."""
    for tpl in TEMPLATES.rglob("*.html"):
        text = tpl.read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text), f"inline script in {tpl.name}"
        assert " on" + "click=" not in text and "javascript:" not in text, tpl.name
        assert "http://" not in text and "https://cdn" not in text, f"external asset in {tpl.name}"


def test_form_inputs_have_labels():
    for name in ("register.html", "login.html", "otp.html", "admin/_election_form.html", "admin/election_detail.html"):
        text = (TEMPLATES / name).read_text()
        ids = re.findall(r'<(?:input|select|textarea)[^>]*\bid="([^"]+)"[^>]*>', text)
        for input_id in ids:
            tag = re.search(rf'<(?:input|select|textarea)[^>]*\bid="{re.escape(input_id)}"[^>]*>', text).group(0)
            if 'type="hidden"' in tag:
                continue
            assert f'for="{input_id}"' in text, f"{name}: #{input_id} has no <label>"


def test_static_assets_served(client):
    for path in (
        "/static/vendor/bootstrap.min.css",
        "/static/vendor/bootstrap.bundle.min.js",
        "/static/vendor/chart.umd.min.js",
        "/static/js/api.js",
        "/static/css/app.css",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, path
        resp.close()


def test_client_side_registration_rules_match_server():
    js = (STATIC / "js" / "pages" / "register.js").read_text()
    assert "[A-Z0-9]{10,20}" in js
    assert "values.password.length < 10" in js
    assert "Passwords do not match" in js


def test_dom_helpers_never_use_innerhtml():
    for js in (STATIC / "js").rglob("*.js"):
        assert not re.search(r"\.(inner|outer)HTML|insertAdjacentHTML|document\.write", js.read_text()), js.name


def test_header_shows_signed_in_role(admin_client, voter_client, world, client):
    voter_html = voter_client("yn1").get("/dashboard").get_data(as_text=True)
    assert re.search(r'id="role-chip"[^>]*>Voter<', voter_html)
    admin_html = admin_client.get("/admin").get_data(as_text=True)
    assert re.search(r'class="role-chip role-chip-staff"[^>]*>Officer<', admin_html)
    assert 'id="role-chip"' not in client.get("/").get_data(as_text=True)
