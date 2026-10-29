# Adamawa State LG Online Voting — Simulated Prototype

> **SIMULATED ACADEMIC PROTOTYPE – NOT AN OFFICIAL ELECTION PLATFORM.**
> This system was built for a BSc research project ("Design and Implementation of a Secure Online Voting System for Local Government Elections in Adamawa State"). It is **not approved by ADSIEC, INEC, NIMC or any authority** and **must not be used for a real public election**. All voters, candidates, parties and results are fictional demo data.

A secure, web-based voting prototype for simulated local government elections across the 21 LGAs of Adamawa State, following the three-tier design in Chapter 3 of the project report:

| Tier | Technology |
|---|---|
| Presentation (`backend/app/templates`, `backend/app/static`) | HTML5 (Jinja2 templates) + CSS3 + Bootstrap 5 + vanilla JavaScript (ES modules, no build step), served by Flask |
| Application | Python 3.14, Flask (app factory + blueprints), JSON REST API at `/api/v1` |
| Data | MySQL 8 via SQLAlchemy + Alembic migrations (SQLite fallback for quick local runs and tests) |

The UI lives in `backend/app/templates/` (HTML) and `backend/app/static/` (CSS, JS, fonts, vendored libraries); see [backend/app/FRONTEND.md](backend/app/FRONTEND.md). Flask serves it from the same origin, so there is nothing to install or build for the frontend.

## Modules (Chapter 3.12)

| Module | Where |
|---|---|
| Voter registration & verification | `/register`, `POST /api/v1/auth/register`, admin `/admin/voters` |
| Voter authentication (+ optional OTP) | `/login`, `/login/otp`, `app/services/auth_service.py`, `otp_service.py` |
| Ballot & candidate display | `/elections/<id>`, `GET /api/v1/elections/<id>/ballot` |
| Vote casting & submission | `POST /api/v1/elections/<id>/votes`, `app/services/voting_service.py` |
| Administration | `/admin`, `/admin/elections`, `/admin/elections/<id>` |
| Result computation & display | `/results/<id>`, `app/services/results_service.py` |
| Audit & monitoring | `/admin/audit-logs`, `app/services/audit_service.py` |

## Project layout

```
backend/
  app/
    __init__.py        application factory
    config.py          environment-based configuration
    extensions.py      db, migrate, CSRF, limiter
    models/            SQLAlchemy models (users, voters, admins, locations, elections, candidates, votes, audit_logs, otp_challenges, user_sessions)
    schemas/           pydantic request validation
    services/          business rules (auth, voting, crypto, results, audit, elections, seed…)
    security/          password hashing, identifier hashing/masking, sessions, RBAC, security headers
    api/               /api/v1 JSON blueprints + OpenAPI
    web/               HTML page routes (server-side access checks)
    templates/         HTML pages (voter/, admin/, errors/)
    static/            css/, js/ (api.js, ui.js, pages/*.js), fonts/, vendor/ (Bootstrap 5.3.8, Chart.js 4.5.1), img/
    cli.py             flask seed | reset-demo | demo-election | create-admin | openapi
  migrations/          Alembic migrations
  scripts/             init_env.py (generate secrets), acceptance.py (end-to-end HTTP run)
  tests/               unit, integration, security, frontend (pages), e2e (Playwright)
docs/                  THREAT_MODEL.md, DECISIONS.md, DATA_MODEL.md, openapi.json
```

## Setup

Prerequisites: Python 3.12+ (developed on 3.14), Homebrew (macOS) or another way to run MySQL 8.

### 1. Install backend dependencies

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # runtime + test/lint tools
.venv/bin/python -m playwright install chromium   # only needed for the browser e2e test
```

There is no separate frontend install: Bootstrap and Chart.js are vendored in `backend/app/static/vendor/`.

### 2. Start MySQL and create the database

```bash
brew install mysql            # once
brew services start mysql
mysql -uroot -e "CREATE DATABASE adamawa_voting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER 'adamawa_app'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
  GRANT ALL PRIVILEGES ON adamawa_voting.* TO 'adamawa_app'@'localhost';"
```

### 3. Configure environment

```bash
cd backend
python scripts/init_env.py --database-url \
  "mysql+pymysql://adamawa_app:choose-a-strong-password@127.0.0.1:3306/adamawa_voting?charset=utf8mb4"
```

This copies `.env.example` to `.env` (mode 600) and generates `SECRET_KEY`, `VOTE_ENCRYPTION_KEY` (AES-256) and `IDENTIFIER_PEPPER`. To skip MySQL, use `--database-url sqlite:///adamawa_voting.db`. `.env` is git-ignored; never commit it.

### 4. Run migrations and seed demo data

```bash
.venv/bin/flask db upgrade
.venv/bin/flask seed                       # prints admin + demo voter passwords ONCE
.venv/bin/flask demo-election --open-now   # open the demo election for 2 hours
```

`flask seed` creates the 21 Adamawa LGAs, DEMO wards and polling units, 24 demo voters (`voter01@example.com` … `voter24@example.com`; 20 verified, 3 pending, 1 rejected), one admin (`admin@example.com` unless `ADMIN_EMAIL` is set), a demo all-LGA chairmanship election with fictional candidates in Yola North, Yola South, Mubi North and Numan, and a draft single-LGA election. Set `ADMIN_PASSWORD` / `DEMO_VOTER_PASSWORD` in `.env` if you want fixed passwords; otherwise random ones are printed once.

Other demo controls:

```bash
flask demo-election --close            # close voting
flask demo-election --publish          # publish results (after close)
flask create-admin --email officer@example.com --name "Officer Name"
```

### 5. Start the app

```bash
.venv/bin/flask run --port 5050
```

Open <http://127.0.0.1:5050>. API documentation: OpenAPI JSON at <http://127.0.0.1:5050/api/v1/openapi.json>, also saved to `docs/openapi.json` by `flask openapi`.

### 6. Run the tests

```bash
cd backend
.venv/bin/pytest                         # all suites (e2e is skipped if Chromium is not installed)
.venv/bin/pytest --cov=app               # with coverage
.venv/bin/pytest tests/e2e               # Playwright browser test only
```

End-to-end acceptance run against a running server (re-seed first, because it closes and publishes the demo election):

```bash
flask reset-demo --yes && flask seed && flask demo-election --open-now
flask run --port 5050 &
ADV_ADMIN_PASSWORD=<printed> ADV_VOTER_PASSWORD=<printed> .venv/bin/python scripts/acceptance.py
```

### 7. Lint and format

```bash
.venv/bin/ruff check .
.venv/bin/ruff format .
```

### 8. Reset local demo data (DESTRUCTIVE)

```bash
FLASK_ENV=development .venv/bin/flask reset-demo --yes   # deletes ALL rows; refuses outside development
.venv/bin/flask seed
```

## Deploying

Free hosting on **PythonAnywhere** (web app, HTTPS and MySQL in one account). The repo includes a WSGI entry point (`backend/wsgi.py`) and a `/healthz` check. Step-by-step guide: [docs/DEPLOY.md](docs/DEPLOY.md).

## How a vote flows

1. A voter registers. The account is **pending** until an administrator verifies it.
2. The verified voter signs in. The dashboard shows only elections for their LGA.
3. The ballot lists only active candidates in the voter's LGA, with nothing preselected. The voter selects one, reviews the choice, and confirms in a dialog that warns the vote is irreversible.
4. Inside one transaction the server locks the voter row, re-checks verification, scope and the voting window, checks for an existing ballot, validates the candidate, and then encrypts and stores the ballot. A `UNIQUE(election_id, voter_id)` constraint is the second layer against double voting.
5. The voter receives a receipt reference that proves the ballot was recorded without revealing the choice (check it at `/receipt-check`).
6. After the administrator closes the election and publishes results, ballots are decrypted **only in aggregate** to compute per-LGA totals. Ties are shown as ties. Races with fewer than 3 votes have their per-candidate totals withheld.

## Security

Treat this section as a description of prototype controls, **not** a claim of election-grade security.

- **Passwords**: bcrypt (cost 12). Generic "Email or password is incorrect" errors, with timing equalised for unknown accounts.
- **Sessions**: the signed, HttpOnly, SameSite=Lax cookie carries only a random token. Sessions live server-side in `user_sessions` and are rotated on login (prevents fixation), revoked on logout/suspension, with a 30-min idle and 8-h absolute expiry. `Secure` cookies + HSTS in the production config.
- **CSRF**: Flask-WTF token required on every state-changing request (`X-CSRFToken` header).
- **Vote secrecy at rest**: AES-256-GCM with a random nonce per ballot, associated data binding each ciphertext to its election and receipt, fixed-length padding, and an integrity hash checked before tallying. The key comes from `VOTE_ENCRYPTION_KEY` (environment), never the database or repository.
- **Identifiers**: voter IDs are stored only as an HMAC (with a separate pepper) plus the last 4 characters for masking. Admin screens show masked email, phone and voter ID. Free-text voter search uses a POST body so personal data never appears in URLs or access logs.
- **Authorization**: role → permission map (`app/security/authz.py`) enforced server-side on every API route and page. Admins cannot vote; voters cannot reach admin pages (403 and audited).
- **Input validation**: pydantic schemas with unknown fields forbidden, strict types, normalisation of email, phone and voter ID, a 64 KB body limit, and ORM-only parameterised queries with LIKE wildcards escaped.
- **Rate limits**: login 10/min, OTP 5/min, vote 5/min per user, registration 5/min (Flask-Limiter; use Redis storage for multi-process deployments).
- **Replay/duplicates**: `Idempotency-Key` on vote submission returns the original receipt for a retried request. Any other second vote gets a 409.
- **Headers**: CSP `default-src 'self'` (no inline scripts, no CDNs at runtime), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, request IDs. CORS headers are sent only to origins listed in `CORS_ORIGINS`.
- **Logging and audit**: structured logs never include request bodies, and sensitive field names are redacted. The append-only `audit_logs` table (ORM blocks update/delete) records logins, failures, verification changes, election/candidate changes, vote outcomes (never the choice), permission denials, CSRF failures and rate-limit hits, with request IDs and keyed IP hashes.
- **OTP**: optional (`OTP_ENABLED=true`). 6-digit codes stored as keyed hashes, 5-minute expiry, 5 attempts. Delivery is a **mock** provider that prints to the dev console only.
- **HTTPS**: run behind a TLS-terminating reverse proxy (e.g. nginx or Caddy) with `FLASK_ENV=production`, which forces `Secure` cookies and HSTS. Use a production WSGI server (e.g. gunicorn), not `flask run`.

### Limitations (also shown in the UI)

- Database encryption alone **does not provide end-to-end verifiability or guaranteed ballot secrecy**. The `votes` table links a voter to an encrypted ballot (required for one-vote enforcement), so anyone holding both the database and the key could link ballots to voters.
- No protection against malware on voters' devices, coercion or vote-buying in unsupervised remote voting, or a compromised server operator.
- No integration with INEC, ADSIEC, NIMC or BVAS registers, and no biometrics. Wards and polling units are placeholders.
- The in-memory rate-limit store resets on restart and is per-process.
- See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the full analysis and [docs/DECISIONS.md](docs/DECISIONS.md) for design decisions.
