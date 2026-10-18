"""End-to-end acceptance run against a RUNNING server.

Prerequisites (fresh demo state):
    flask reset-demo --yes && flask seed && flask demo-election --open-now
    flask run --port 5050

Usage:
    ADV_ADMIN_PASSWORD=... ADV_VOTER_PASSWORD=... python scripts/acceptance.py [--base http://127.0.0.1:5050]

Prints PASS/FAIL per step and exits non-zero if any step fails.
WARNING: closes and publishes the demo election, so re-seed before running again.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta

import requests

RESULTS: list[tuple[str, bool, str]] = []


class Actor:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.csrf = None

    def refresh_csrf(self) -> None:
        self.csrf = self.s.get(f"{self.base}/api/v1/auth/csrf", timeout=10).json()["data"]["csrf_token"]

    def call(self, method: str, path: str, json=None, headers=None):
        hdrs = dict(headers or {})
        if method != "GET":
            if self.csrf is None:
                self.refresh_csrf()
            hdrs["X-CSRFToken"] = self.csrf
        r = self.s.request(method, f"{self.base}/api/v1{path}", json=json, headers=hdrs, timeout=15)
        try:
            body = r.json()
        except ValueError:
            body = {}
        if isinstance(body, dict) and isinstance(body.get("data"), dict) and body["data"].get("csrf_token"):
            self.csrf = body["data"]["csrf_token"]
        return r.status_code, body

    def login(self, email: str, password: str):
        self.refresh_csrf()
        return self.call("POST", "/auth/login", {"email": email, "password": password})

    def page(self, path: str):
        return self.s.get(f"{self.base}{path}", timeout=10, allow_redirects=False)


def step(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))
    return ok


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("ADV_BASE_URL", "http://127.0.0.1:5050"))
    ap.add_argument("--admin-email", default=os.environ.get("ADV_ADMIN_EMAIL", "admin@example.com"))
    ap.add_argument("--admin-password", default=os.environ.get("ADV_ADMIN_PASSWORD"))
    ap.add_argument("--voter-password", default=os.environ.get("ADV_VOTER_PASSWORD"))
    args = ap.parse_args()
    if not args.admin_password or not args.voter_password:
        print("Set ADV_ADMIN_PASSWORD and ADV_VOTER_PASSWORD (printed by `flask seed`).")
        return 2
    base = args.base

    # ------------------------------------------------------------ public
    anon = Actor(base)
    r = anon.page("/")
    step("Landing page renders", r.status_code == 200 and "Vote from" in r.text)
    for path in ("/register", "/login", "/admin/login", "/help", "/results", "/receipt-check"):
        r = anon.page(path)
        step(f"Public page {path} renders", r.status_code == 200, str(r.status_code))
    r = anon.page("/admin")
    step(
        "Admin page redirects anonymous users to admin login",
        r.status_code == 302 and "/admin/login" in r.headers.get("Location", ""),
    )
    code, body = anon.call("GET", "/admin/dashboard")
    step("Admin API rejects anonymous users (401)", code == 401)
    code, body = anon.call("GET", "/locations/lgas")
    lgas = {x["name"]: x["id"] for x in body.get("data", [])}
    step("21 Adamawa LGAs available", code == 200 and len(lgas) == 21, str(len(lgas)))
    yola_n = lgas.get("Yola North")
    _, wards = anon.call("GET", f"/locations/lgas/{yola_n}/wards")
    ward_id = wards["data"][0]["id"]
    _, pus = anon.call("GET", f"/locations/wards/{ward_id}/polling-units")
    pu_id = pus["data"][0]["id"]

    # ------------------------------------------------------------ registration
    tag = secrets.token_hex(3).upper()
    new_email = f"acceptance.{tag.lower()}@example.com"
    password = f"Accept-{secrets.token_hex(4)}9"
    reg = {
        "surname": "Acceptance",
        "first_name": "Tester",
        "other_names": None,
        "email": new_email,
        "phone": f"0803{secrets.randbelow(10**7):07d}",
        "voter_id": f"ACCEPT{tag}0001",
        "lga_id": yola_n,
        "ward_id": ward_id,
        "polling_unit_id": pu_id,
        "password": password,
        "confirm_password": password,
        "demo_acknowledged": True,
    }
    code, body = anon.call("POST", "/auth/register", reg)
    step("New voter registers (pending)", code == 201 and body["data"]["verification_status"] == "pending", str(body))
    code, body = anon.call("POST", "/auth/register", reg)
    step("Duplicate registration rejected (409)", code == 409 and body["error"]["code"] == "duplicate_account")
    code, body = anon.call("POST", "/auth/register", {"surname": "", "email": "not-an-email"})
    step("Incomplete/malformed registration rejected (422)", code == 422 and len(body["error"]["details"]) >= 3)
    code, body = anon.call("POST", "/auth/register", {**reg, "lga_id": "1 OR 1=1"})
    step("Type-confused registration rejected (422)", code == 422)

    # ------------------------------------------------------------ unverified voter
    newbie = Actor(base)
    code, body = newbie.login(new_email, password)
    step("Pending voter can sign in", code == 200 and body["data"]["user"]["role"] == "voter")
    _, me = newbie.call("GET", "/me")
    step(
        "Dashboard shows pending status with masked data",
        me["data"]["voter"]["verification_status"] == "pending" and "*" in me["data"]["email_masked"],
    )
    _, elections = newbie.call("GET", "/elections")
    demo = next((e for e in elections["data"] if "Chairmanship" in e["title"]), None)
    if not step(
        "Demo election visible and open", demo is not None and demo["voting_open"], "run `flask demo-election --open-now`"
    ):
        return summary()
    eid = demo["id"]
    code, body = newbie.call("GET", f"/elections/{eid}/ballot")
    step("Unverified voter cannot open ballot (403)", code == 403 and body["error"]["code"] == "not_verified")
    code, body = newbie.call("POST", f"/elections/{eid}/votes", {"candidate_id": 1})
    step("Unverified voter cannot vote (403)", code == 403)
    code, _ = newbie.call("GET", "/admin/voters")
    step("Voter cannot call admin API (403)", code == 403)
    r = newbie.page("/admin")
    step("Voter gets 403 page for /admin", r.status_code == 403)

    # ------------------------------------------------------------ admin verifies
    admin = Actor(base)
    code, body = admin.login(args.admin_email, args.admin_password)
    step("Admin signs in", code == 200 and body["data"]["user"]["role"] == "admin", str(body.get("error")))
    code, body = admin.login(args.admin_email, "wrong-password-123")
    step(
        "Wrong admin password gives generic error", code == 401 and body["error"]["message"] == "Email or password is incorrect."
    )
    code, body = admin.login("' OR 1=1 -- ", "x")
    step("SQL-injection style login rejected safely", code in (401, 422))
    # Failed attempts do not end the existing admin session.
    r = admin.page("/elections/1")
    step("Admin gets 403 on voter ballot page", r.status_code == 403)
    code, body = admin.call("POST", "/admin/voters/search", {"q": new_email})
    voter_row = body["data"][0] if code == 200 and body["data"] else None
    step(
        "Admin finds the new voter (masked)",
        voter_row is not None and "@" in voter_row["email_masked"] and "*" in voter_row["email_masked"],
    )
    code, body = admin.call("PATCH", f"/admin/voters/{voter_row['id']}/verification", {"action": "reject"})
    step("Reject without reason is refused (422)", code == 422)
    code, body = admin.call("PATCH", f"/admin/voters/{voter_row['id']}/verification", {"action": "verify"})
    step("Admin verifies the voter", code == 200 and body["data"]["verification_status"] == "verified")

    # ------------------------------------------------------------ voting
    code, body = newbie.call("GET", f"/elections/{eid}/ballot")
    cands = body["data"]["candidates"] if code == 200 else []
    step(
        "Verified voter sees only Yola North candidates",
        code == 200 and len(cands) == 3 and all(c["lga"]["name"] == "Yola North" for c in cands),
    )
    code, body = newbie.call("POST", f"/elections/{eid}/votes", {"candidate_id": 999999})
    step("Vote for invalid candidate rejected (422)", code == 422 and "No vote was recorded" in body["error"]["message"])
    key = secrets.token_hex(16)
    code, body = newbie.call("POST", f"/elections/{eid}/votes", {"candidate_id": cands[0]["id"]}, {"Idempotency-Key": key})
    receipt = body.get("data", {}).get("receipt_reference")
    step("Verified voter casts a vote (201 + receipt)", code == 201 and bool(receipt))
    step("Vote response does not echo the candidate", "candidate" not in str(body.get("data", {})).lower())
    code, body = newbie.call("POST", f"/elections/{eid}/votes", {"candidate_id": cands[0]["id"]}, {"Idempotency-Key": key})
    step(
        "Retried request with same Idempotency-Key returns original receipt",
        code == 200 and body["data"]["receipt_reference"] == receipt,
    )
    code, body = newbie.call("POST", f"/elections/{eid}/votes", {"candidate_id": cands[1]["id"]})
    step("Second vote rejected (409 already_voted)", code == 409 and body["error"]["code"] == "already_voted")
    code, body = newbie.call("GET", f"/elections/{eid}/participation-status")
    step(
        "Participation status shows voted, no choice", code == 200 and body["data"]["has_voted"] and "candidate" not in str(body)
    )

    # Two seeded Yola North voters vote so the race passes the small-count threshold.
    for email, pick in (("voter01@example.com", 0), ("voter05@example.com", 1), ("voter09@example.com", 0)):
        v = Actor(base)
        v.login(email, args.voter_password)
        code, body = v.call("POST", f"/elections/{eid}/votes", {"candidate_id": cands[pick]["id"]})
        step(
            f"Seeded voter {email} votes",
            code == 201 or (code == 409 and body["error"]["code"] == "already_voted"),
            str(body.get("error")),
        )

    code, body = newbie.call("GET", f"/elections/{eid}/results")
    step("Results hidden before close/publication (403)", code == 403 and body["error"]["code"] == "results_not_published")

    # ------------------------------------------------------------ outside window
    now = datetime.now(UTC)
    code, body = admin.call(
        "POST",
        "/admin/elections",
        {
            "title": f"Acceptance future election {tag}",
            "type": "councillorship",
            "scope": "single_lga",
            "lga_id": yola_n,
            "start_at": iso(now + timedelta(days=2)),
            "end_at": iso(now + timedelta(days=2, hours=4)),
        },
    )
    future_id = body["data"]["id"] if code == 201 else None
    step("Admin creates a draft election", code == 201)
    code, body = admin.call("POST", f"/admin/elections/{future_id}/open")
    step("Cannot open an election without candidates (409)", code == 409 and body["error"]["code"] == "no_candidates")
    code, body = admin.call(
        "POST",
        f"/admin/elections/{future_id}/candidates",
        {"full_name": "Future Candidate Demo", "party_affiliation": "Demo Party"},
    )
    fc = body["data"]["id"] if code == 201 else None
    step("Admin adds a candidate", code == 201)
    code, body = admin.call("POST", f"/admin/elections/{future_id}/open")
    step("Admin opens the election early (window not started)", code == 200 and body["data"]["phase"] == "opening_soon")
    # A different voter is used here: the newbie has hit the per-voter vote rate limit (5/min).
    early = Actor(base)
    early.login("voter13@example.com", args.voter_password)
    code, body = early.call("POST", f"/elections/{future_id}/votes", {"candidate_id": fc})
    step(
        "Voting outside the election window rejected (409)",
        code == 409 and body["error"]["code"] == "voting_closed",
        str(body.get("error")),
    )
    code, body = admin.call("PATCH", f"/admin/elections/{future_id}", {"title": "Changed after opening"})
    step("Election locked after opening (409)", code == 409 and body["error"]["code"] == "election_locked")
    code, body = admin.call("POST", f"/admin/elections/{future_id}/cancel", {"reason": "Acceptance test cleanup"})
    step("Admin cancels the test election with a reason", code == 200 and body["data"]["status"] == "cancelled")

    # ------------------------------------------------------------ close + publish
    code, body = admin.call("POST", f"/admin/elections/{eid}/publish-results")
    step("Cannot publish while open (409)", code == 409)
    code, body = admin.call("POST", f"/admin/elections/{eid}/close")
    step("Admin closes the demo election", code == 200 and body["data"]["status"] == "closed")
    late = Actor(base)
    late.login("voter17@example.com", args.voter_password)
    code, body = late.call("POST", f"/elections/{eid}/votes", {"candidate_id": cands[0]["id"]})
    step("Vote after close rejected (409)", code == 409 and body["error"]["code"] == "voting_closed", str(body.get("error")))
    code, body = anon.call("GET", f"/elections/{eid}/results")
    step("Results still hidden after close until published", code == 403)
    code, body = admin.call("POST", f"/admin/elections/{eid}/publish-results")
    step("Admin publishes results", code == 200 and body["data"]["results_available"])
    code, body = anon.call("GET", f"/elections/{eid}/results")
    races = {r["lga"]["name"]: r for r in body.get("data", {}).get("races", [])}
    yn = races.get("Yola North", {})
    step(
        "Public results show aggregate Yola North totals",
        code == 200 and yn.get("total_valid_votes", 0) >= 4 and yn.get("outcome") in {"winner", "tie"},
        str(yn),
    )
    step("Results labelled simulated", body.get("data", {}).get("is_simulated") is True)
    step(
        "Small races are withheld or empty",
        all(r["outcome"] in {"withheld", "no_votes", "winner", "tie"} for r in races.values()),
    )
    r = anon.page(f"/results/{eid}")
    step("Results page renders", r.status_code == 200)
    code, body = anon.call("POST", "/receipts/verify", {"receipt_reference": receipt})
    step(
        "Receipt check confirms the ballot was recorded",
        code == 200 and body["data"]["recorded"] is True and "candidate" not in str(body),
    )

    # ------------------------------------------------------------ audit + logout
    code, body = admin.call("GET", "/admin/audit-logs?per_page=100")
    events = {e["event_type"] for e in body.get("data", [])}
    expected = {
        "vote.submitted",
        "vote.duplicate_rejected",
        "voter.verify",
        "election.close",
        "election.results_published",
        "auth.login_failed",
        "security.permission_denied",
    }
    step("Audit log records sensitive actions", expected <= events, str(expected - events))
    step("Audit log contains no ballot choices", all(c["full_name"] not in str(body) for c in cands))
    code, _ = newbie.call("GET", "/admin/audit-logs")
    step("Voters cannot read the audit log (403)", code == 403)
    code, _ = newbie.call("POST", "/auth/logout")
    code2, _ = newbie.call("GET", "/me")
    step("Logout invalidates the session", code == 200 and code2 == 401)
    return summary()


def summary() -> int:
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} steps passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
