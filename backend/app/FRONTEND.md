# Frontend — presentation tier (HTML5 / CSS3 / JavaScript / Bootstrap 5)

The user interface lives in `templates/` and `static/` next to this file. It has no build step and needs no Node.js. Flask serves it from the same origin. Pages therefore share the session cookie and CSRF token with the API, and the server checks each user's role **before** it renders a page.

```
backend/app/
  templates/                 Jinja2 HTML pages
    base.html                layout: navigation, skip link, CSRF meta tag, footer
    index.html help.html     landing and help/limitations
    register.html            voter registration
    login.html otp.html      voter/admin sign-in, optional one-time code
    results_list.html results.html receipt_check.html
    voter/                   dashboard.html, ballot.html (review + confirm modal), receipt.html
    admin/                   dashboard.html, voters.html, elections.html, election_detail.html, audit.html
    errors/                  403.html, 404.html, error.html
  static/
    css/app.css              design system from design.md (monochrome, Inter, flat), focus styles, ballot layout
    js/api.js                fetch() wrapper for /api/v1 (CSRF header, error envelope)
    js/ui.js                 DOM helpers (textContent only, never innerHTML), formatting, masking
    js/common.js             sign-out button
    js/pages/*.js            one ES module per page
    vendor/                  Bootstrap 5.3.8 and Chart.js 4.5.1 (vendored so the CSP can be 'self' only)
    fonts/                   Inter (variable), self-hosted for the CSP
    img/favicon.svg
```

## How pages work

1. Flask renders a page shell from `templates/` after checking the user's role (voter pages need a voter, `/admin/*` pages need an administrator).
2. The page's module in `static/js/pages/` loads its data from the JSON API (`/api/v1/...`) with `fetch()` and builds the DOM with `textContent`.
3. Every state-changing request sends the CSRF token from `<meta name="csrf-token">` in the `X-CSRFToken` header.

## Rules for editing

- **No inline `<script>`, no `onclick=` attributes, no CDN links.** The Content-Security-Policy only allows files from this origin. Add new scripts as files in `static/js/pages/` and include them with `{% block scripts %}`.
- Insert API data with `textContent` (see the `h()` helper in `ui.js`), never `innerHTML`.
- Never preselect a ballot option, and never store a ballot choice in `localStorage`, `sessionStorage` or the URL.
- Give every form control a `<label for=…>`.

## Running

From `backend/`: `.venv/bin/flask run --port 5050`, then open <http://127.0.0.1:5050>. Setup steps are in the root [README](../../README.md). Page tests are in `backend/tests/frontend/`, and the Playwright browser test is in `backend/tests/e2e/`.
