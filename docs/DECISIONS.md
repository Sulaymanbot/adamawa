# Design Decisions

Decisions taken while building the prototype where the PRD or Chapter 3 left room for interpretation. In each case the safer or simpler option was chosen.

## Stack and structure

1. **Plain HTML instead of React.** The build instruction overrode PRD §5/§9: the UI is Jinja2 + Bootstrap 5 + vanilla JS modules. This also matches Chapter 3 ("HTML5, CSS3, JavaScript, Bootstrap 5"). Pages are thin shells that call the `/api/v1` JSON API, so the API stays the tested contract. The UI lives in `backend/app/templates` and `backend/app/static` (Flask defaults), so the whole app deploys as one service. Flask serves it from the same origin rather than as a separate static site. That keeps the server-side role checks before a page renders, the session cookie and CSRF token without CORS, and a `'self'`-only CSP.
2. **Vendored front-end libraries.** Bootstrap 5.3.8 and Chart.js 4.5.1 are stored in `backend/app/static/vendor/` (source-map comments removed) so the CSP can be `'self'` only and nothing loads from a CDN at runtime.
3. **The Python virtualenv was recreated.** The existing `backend/.venv` had been created at another path (`/Users/mac/Desktop/sadiq/backend/.venv`), so its scripts pointed to a missing interpreter. It was recreated in place with the same Python 3.14.
4. **No package swaps were needed for Python 3.14.** All chosen packages installed from wheels. pydantic was chosen over marshmallow for validation. A double-submit token library was not needed because Flask-WTF CSRF works for JSON requests via a header.
5. **MySQL 8 via PyMySQL.** MySQL was installed with Homebrew. `DATABASE_URL` also accepts SQLite, and the test suite always uses SQLite (in memory, or a temporary file for migration tests). Migrations use a naming convention and `render_as_batch` so they run on both.

## Data model

6. **PRD §7 tables, mapped to the Chapter 3 ERD** (see `DATA_MODEL.md`). Extra tables: `user_sessions` (revocable server-side sessions) and `otp_challenges`.
7. **No plaintext voter ID or NIN.** The ERD's `nin` column was dropped. The simulated voter ID is stored as an HMAC-SHA256 (keyed with `IDENTIFIER_PEPPER`) plus its last 4 characters for masking. Registration asks for a *demo* voter ID only, never a NIN, so users are not invited to type real national identifiers.
8. **Enums as strings plus CHECK constraints** instead of native ENUMs, for portability and simpler migrations.
9. **Timestamps are naive UTC truncated to whole seconds.** MySQL `DATETIME` has no timezone and rounds fractional seconds. Without truncation, a result published "now" was stored up to a second in the future and stayed hidden (found and fixed during the MySQL acceptance run). The UI displays times in West Africa Time (Africa/Lagos), and admin datetime inputs are interpreted as WAT.

## Elections and voting

10. **Scopes.** `all_lgas` means simultaneous chairmanship races, one per LGA, and each voter sees only their LGA's candidates. `single_lga` means one LGA only. Voters out of scope get a 404 (the election is not revealed).
11. **Lifecycle:** draft → scheduled → open → closed → archived, with cancel allowed from draft/scheduled/open (a reason is required if open). Opening requires at least one active candidate and a closing time still in the future. Voting needs `status == open` **and** `start_at ≤ now < end_at`, so an election opened early shows "opening soon".
12. **Locking after voting starts.** Election details and candidates are editable only in draft/scheduled. `DEMO_ADMIN_OVERRIDE=true` (refused in production config) allows only title/description/closing-time edits and candidate deactivation while open, and each such change is audited with a `[DEMO OVERRIDE]` prefix.
13. **Votes are final.** No re-voting. The confirmation modal says so.
14. **Idempotency.** The ballot page creates one `Idempotency-Key` per page load. A retry with the same key returns the original receipt (200). Any other second submission is a 409.
15. **Receipts.** A random 16-character reference (no ambiguous characters) is shown to the voter and can be checked publicly at `/receipt-check`. The check confirms only that a ballot exists, never its content.

## Results

16. **Results are computed only after close + publish**, on request, by decrypting in memory. There is no live tally and no admin "preview" before publication.
17. **Scheduled publication.** `publish_at` may be in the future, and results stay hidden until then. Results can also be hidden again.
18. **Tie handling.** If two or more candidates share the top total, the outcome is `tie`, no winner is declared, and the UI says resolution happens outside the system.
19. **Small-count suppression.** Races with fewer than `RESULTS_MIN_RACE_VOTES` (default 3) valid votes have per-candidate totals withheld. Otherwise an admin could combine a 1-vote race with participation data to learn an individual's choice. Results are aggregated per LGA only (no ward or polling-unit breakdown).
20. **Public results.** Published simulated results are viewable without signing in, labelled "SIMULATED".

## Authentication and privacy

21. **Unverified voters can sign in** to see their status, but cannot open a ballot or vote.
22. **Suspended accounts** cannot sign in, and all their sessions are revoked immediately. A "this account is not active" message appears only after the correct password is given, so it does not reveal whether an account exists.
23. **Duplicate registration** returns one generic 409 without saying which field matched, to limit account enumeration.
24. **Voter text search moved to `POST /admin/voters/search`.** During acceptance testing an email address appeared in the dev server's access log via `?q=`. `GET /admin/voters` now accepts filters only and rejects `q`.
25. **LIKE wildcards escaped** in voter search and the audit event-type filter (found by a security test: `%` matched every voter).
26. **IP addresses** in the audit log are stored as a truncated keyed hash (`AUDIT_IP_MODE=hash`, or `none`).
27. **OTP** is behind `OTP_ENABLED` with a mock provider (dev console / in-memory outbox in tests). The production config raises an error if OTP is enabled without a real provider.

## Seed data

28. **LGA names are the 21 official Adamawa LGAs.** Wards and polling units are generated placeholders prefixed "DEMO". Candidates and parties are obviously fictional. Demo emails use the reserved `example.com` domain.
29. **Credentials.** `flask seed` uses `ADMIN_PASSWORD` / `DEMO_VOTER_PASSWORD` if set (and does not echo them), otherwise generates random passwords and prints them once.
30. **`reset-demo` deletes rows** (it does not drop tables, so the Alembic version is kept) and refuses to run unless `FLASK_ENV=development`.

## Testing

31. "Frontend tests" are Flask test-client page tests plus a Playwright (Chromium, headless) browser test that runs the full workflow. The e2e test skips itself if Playwright or Chromium is missing.
32. Tests keep one app context open for convenience, so a fixture clears Flask-WTF's per-request CSRF cache on `g` to mimic production's fresh per-request context. No security control is relaxed in tests (CSRF stays on). Rate limiting is off by default in tests and switched on in its dedicated tests.
