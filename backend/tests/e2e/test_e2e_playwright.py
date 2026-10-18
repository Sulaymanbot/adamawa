"""Browser end-to-end test (Playwright, Chromium, headless).

register -> admin verifies -> voter logs in -> votes -> duplicate rejected ->
admin closes -> publishes -> results visible.

Skipped automatically if Playwright or its Chromium build is not installed:
    pip install playwright && python -m playwright install chromium
"""

from __future__ import annotations

import re
import socket
import threading
from datetime import timedelta

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

from werkzeug.serving import make_server  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Election, Voter, utcnow  # noqa: E402
from app.services import seed_service, voting_service  # noqa: E402

pytestmark = pytest.mark.e2e

ADMIN_PW = "AdminPass123"
VOTER_PW = "VoterPass123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("e2e") / "e2e.db"
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}"})
    with app.app_context():
        db.create_all()
        result = seed_service.seed_demo(admin_email="admin@example.com", admin_password=ADMIN_PW, voter_password=VOTER_PW)
        election = result["election"]
        election.start_at = utcnow() - timedelta(minutes=5)
        election.end_at = utcnow() + timedelta(hours=2)
        election.status = "open"
        db.session.commit()
        # Two seeded Yola North voters vote first so the race clears the
        # small-count threshold and per-candidate totals are published.
        yola_north = [v for v in db.session.query(Voter).filter_by(verification_status="verified") if v.lga.name == "Yola North"][
            :2
        ]
        cands = [c for c in election.candidates if c.lga.name == "Yola North"]
        with app.test_request_context():
            for voter, cand in zip(yola_north, cands, strict=False):
                voting_service.cast_vote(voter.user, election.id, cand.id, None)
        election_id = election.id

    port = _free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"url": f"http://127.0.0.1:{port}", "election_id": election_id, "app": app}
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    try:
        pw = playwright_sync.sync_playwright().start()
        browser = pw.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium for Playwright is not available: {exc}")
    yield browser
    browser.close()
    pw.stop()


def login(page, base, email, password, admin=False):
    page.goto(f"{base}/{'admin/' if admin else ''}login")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("#login-submit")
    page.wait_for_url(re.compile(r"/(admin|dashboard)$"))


def logout(page):
    page.click("#account-menu")  # sign-out lives in the avatar menu
    page.click("#logout-btn")
    page.wait_for_url(re.compile(r"/$"))


def test_full_voting_workflow(live_server, browser):
    base, eid = live_server["url"], live_server["election_id"]
    ctx = browser.new_context()
    page = ctx.new_page()
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

    # Landing page shows the prototype warning.
    page.goto(base)
    assert page.get_by_role("heading", name="Vote from anywhere.").is_visible()

    # --- Registration: client-side validation, then a real submission.
    page.goto(f"{base}/register")
    page.click("#register-submit")
    assert page.locator(".is-invalid").count() >= 5
    assert "Please fix" in page.locator("#register-alert").inner_text()
    page.fill("#surname", "Playwright")
    page.fill("#first_name", "Hauwa")
    page.fill("#email", "e2e.voter@example.com")
    page.fill("#phone", "0809 111 2222")
    page.fill("#voter_id", "E2EDEMO00001")
    page.select_option("#lga_id", label="Yola North")
    page.wait_for_selector("#ward_id:not([disabled])")
    page.select_option("#ward_id", index=1)
    page.wait_for_selector("#polling_unit_id:not([disabled])")
    page.select_option("#polling_unit_id", index=1)
    page.fill("#password", "E2ePassword99")
    page.fill("#confirm_password", "E2ePassword99x")
    page.check("#demo_acknowledged")
    page.click("#register-submit")
    assert "Passwords do not match" in page.locator("#confirm_password-error").inner_text()
    page.fill("#confirm_password", "E2ePassword99")
    page.click("#register-submit")
    page.wait_for_selector("#register-success:not(.d-none)")
    assert "verify your account" in page.locator("#register-next").inner_text()

    # --- New voter sees pending status and cannot vote yet.
    login(page, base, "e2e.voter@example.com", "E2ePassword99")
    page.wait_for_selector("#profile .status")
    assert "pending" in page.locator("#profile").inner_text().lower()
    assert page.locator("a:has-text('Go to ballot')").count() == 0
    # Voter cannot reach admin pages.
    resp = page.goto(f"{base}/admin")
    assert resp.status == 403 and page.get_by_text("Access denied").is_visible()
    page.goto(f"{base}/dashboard")
    logout(page)

    # --- Admin verifies the voter.
    login(page, base, "admin@example.com", ADMIN_PW, admin=True)
    assert page.locator("nav >> text=Audit log").is_visible()
    page.goto(f"{base}/admin/voters")
    page.fill("#f-q", "e2e.voter@example.com")
    page.click("#voter-filters button[type=submit]")
    page.wait_for_selector("button[aria-label='Verify Hauwa Playwright']")
    assert "e2e.voter@example.com" not in page.locator("#voters-table").inner_text(), "email must be masked"
    page.click("button[aria-label='Verify Hauwa Playwright']")
    page.wait_for_selector("#verify-modal.show")
    page.click("#verify-submit")
    page.wait_for_selector("#voters-alert .alert-success")
    logout(page)

    # --- Verified voter votes: nothing preselected, review, confirm.
    login(page, base, "e2e.voter@example.com", "E2ePassword99")
    page.click("a:has-text('Go to ballot')")
    page.wait_for_selector("#ballot-form:not(.d-none)")
    radios = page.locator("input[name=candidate_id]")
    assert radios.count() == 3
    assert page.locator("input[name=candidate_id]:checked").count() == 0
    page.click("#review-btn")
    assert "Select one candidate" in page.locator("#choose-error").inner_text()
    radios.nth(1).focus()
    page.keyboard.press("Space")
    chosen = page.locator("label.ballot-option.selected .candidate-name").inner_text()
    page.click("#review-btn")
    assert page.locator("#review-name").inner_text() == chosen
    page.click("#change-btn")
    assert page.locator("input[name=candidate_id]:checked").count() == 1
    page.click("#review-btn")
    page.click("#confirm-open-btn")
    page.wait_for_selector("#confirm-modal.show")
    assert "cannot be undone" in page.locator("#confirm-modal").inner_text()
    page.click("#submit-vote-btn")
    page.wait_for_url(re.compile(rf"/elections/{eid}/receipt"))
    page.wait_for_selector(".receipt-ref")
    receipt = page.locator(".receipt-ref").inner_text()
    assert re.fullmatch(r"[A-Z0-9]{4}(-[A-Z0-9]{4}){3}", receipt)
    assert chosen not in page.content(), "the receipt page must not reveal the choice"

    # --- Duplicate vote rejected (UI and API).
    page.goto(f"{base}/elections/{eid}")
    page.wait_for_selector("#ballot-alert .alert")
    assert "already voted" in page.locator("#ballot-alert").inner_text()
    status = page.evaluate(
        """async (eid) => {
            const token = document.querySelector('meta[name=csrf-token]').content;
            const r = await fetch(`/api/v1/elections/${eid}/votes`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': token},
                body: JSON.stringify({candidate_id: 1}),
            });
            return [r.status, (await r.json()).error.code];
        }""",
        eid,
    )
    assert status == [409, "already_voted"]
    logout(page)

    # --- Admin closes the election and publishes results.
    login(page, base, "admin@example.com", ADMIN_PW, admin=True)
    page.goto(f"{base}/admin/elections/{eid}")
    page.click("#action-buttons button:has-text('Close voting')")
    page.wait_for_selector("#action-modal.show")
    page.click("#action-confirm")
    page.wait_for_selector("#detail-alert .alert-success")
    page.click("#publish-area button:has-text('Publish results')")
    page.wait_for_selector("#publish-area a:has-text('View published results')")
    page.goto(f"{base}/admin/audit-logs")
    page.wait_for_selector("#audit-table table")
    audit_text = page.locator("#audit-table").inner_text()
    assert "election.results_published" in audit_text and "vote.submitted" in audit_text
    logout(page)

    # --- Anyone can now see aggregate, simulated results with table + chart.
    page.goto(f"{base}/results/{eid}")
    page.wait_for_selector("#results-races section")
    races = page.locator("#results-races").inner_text()
    assert "Yola North LGA" in races and "Valid votes in this race: 3" in races
    assert page.locator("#results-races canvas").count() >= 1
    assert "SIMULATED" in page.content()
    page.goto(f"{base}/receipt-check")
    page.fill("#receipt_reference", receipt)
    page.click("#receipt-form button")
    page.wait_for_selector("#receipt-alert .alert-success")

    ctx.close()
    # Network errors from the deliberate 403/409 checks above are expected; any
    # other console error means a page script broke.
    assert not [e for e in console_errors if not e.startswith("Failed to load resource")], console_errors


def test_election_row_reflects_close(live_server):
    with live_server["app"].app_context():
        e = db.session.get(Election, live_server["election_id"])
        assert e.status == "closed" and e.results_published_at is not None
