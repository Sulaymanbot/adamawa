# Deploying (free): Render + Aiven MySQL

**Recommended setup for a school demo:**

| Piece | Service | Free tier |
|---|---|---|
| Web app (Flask + gunicorn) | [Render](https://render.com) Web Service | Free. Sleeps after ~15 min idle; first visit after that takes ~30–60 s to wake |
| Database (MySQL 8) | [Aiven](https://aiven.io) for MySQL | Free plan: 1 node, small storage, always on |

Why these two: Render deploys straight from GitHub on every push and gives HTTPS automatically. It has no MySQL, though (its free Postgres is deleted after 30 days), so the database goes on Aiven's free MySQL, which matches Chapter 3 of the report (MySQL 8).

Alternative (single service, no sleeping): **PythonAnywhere** free plan includes MySQL, but it is set up by hand rather than deployed from git.

---

## 1. Push the code to GitHub

```bash
cd adamawa-online-voting
git push -u origin main
```

`backend/.env` is git-ignored, so no secrets are pushed.

## 2. Create the free MySQL database (Aiven)

1. Sign up at aiven.io, then **Create service → MySQL → Free plan**, and pick a region close to you (e.g. Europe).
2. When it is running, open the service's **Overview** page:
   - Copy the **Service URI**. It looks like `mysql://avnadmin:PASSWORD@HOST:PORT/defaultdb?ssl-mode=REQUIRED`.
   - Download the **CA certificate** (`ca.pem`).
3. Turn the URI into the app's `DATABASE_URL` by **removing `?ssl-mode=REQUIRED`** (the app sets up TLS from the CA certificate instead):
   ```
   mysql://avnadmin:PASSWORD@HOST:PORT/defaultdb
   ```
   (`mysql://` is fine; the app switches it to the PyMySQL driver.)

## 3. Generate the app's secrets

```bash
cd backend
.venv/bin/python scripts/gen_secrets.py
```

You only need `VOTE_ENCRYPTION_KEY` from the output, because Render generates the other two. **Keep it safe and never change it** while the database holds votes. If it changes, every stored ballot becomes unreadable.

## 4. Create the Render service from the blueprint

1. Sign up at render.com with GitHub.
2. **New → Blueprint**, then pick the `adamawa-online-voting` repo. Render reads `render.yaml`.
3. Render asks for the values marked `sync: false`:

| Variable | Value |
|---|---|
| `VOTE_ENCRYPTION_KEY` | from step 3 |
| `DATABASE_URL` | the URL from step 2 (without `?ssl-mode=...`) |
| `DB_SSL_CA_PEM` | paste the **whole contents** of Aiven's `ca.pem` |
| `TEST_ADMIN_PASSWORD` | a password for `admin@example.com` (10+ chars, letter + number) |
| `TEST_VOTER_PASSWORD` | a password for `voter1…voter5@example.com` |

4. Click **Apply**. The first deploy takes a few minutes. On every start, the service:
   - runs the database migrations (`flask db upgrade`),
   - creates the test accounts **only if the database is empty** (`flask seed-test-users --if-empty`): 21 LGAs, 1 admin and 5 verified voters,
   - starts gunicorn. Render checks `/healthz` to know the app is up.
5. Open `https://adamawa-vote.onrender.com` (or whatever name Render shows) and sign in.

After this, every `git push` to `main` redeploys automatically.

## Resetting the online database

Render's free plan has no shell. To start fresh, run this from your laptop against the Aiven database:

```bash
cd backend
export DATABASE_URL='mysql://avnadmin:PASSWORD@HOST:PORT/defaultdb'
export DB_SSL_CA=/path/to/ca.pem
FLASK_ENV=development .venv/bin/flask reset-demo --yes
```

The next restart or deploy on Render re-creates the test accounts. Use **Manual Deploy → Restart** in Render.

## Notes and limits

- **Cold starts:** the free web service sleeps when idle. Open the site a minute before a demo.
- **Rate limits** are kept in memory, per server process, and reset when the service restarts. That's fine for one free instance.
- **Production settings** (`FLASK_ENV=production`): Secure HTTPS-only cookies and HSTS are switched on, the app trusts exactly one proxy hop (`TRUST_PROXY=true`, needed for HTTPS detection and correct client IPs in audit logs), logs are JSON, and the demo admin override is refused.
- `ALLOW_DEMO_SEED=true` is what lets the test accounts be created on a server. Default passwords are refused there; you must set your own.
