# Deploying (free): PythonAnywhere

The PythonAnywhere free plan includes the web app, HTTPS and a MySQL database in one account. Replace `USERNAME` below with your PythonAnywhere username.

---

## 1. Get the code onto PythonAnywhere

Open a **Bash console** (Consoles tab):

```bash
git clone https://github.com/Sulaymanbot/adamawa.git
cd adamawa/backend
mkvirtualenv --python=python3.13 adamawa-venv   # or the newest Python 3.12+ offered
pip install -r requirements.txt
```

`backend/.env` is git-ignored, so no secrets come from GitHub. You create it in step 3.

## 2. Create the MySQL database

On the **Databases** tab:

1. Set a MySQL password.
2. Create a database named `adamawa`. PythonAnywhere names it `USERNAME$adamawa`.
3. Note the host: `USERNAME.mysql.pythonanywhere-services.com`.

## 3. Create `backend/.env`

Generate the secrets:

```bash
cd ~/adamawa/backend
python scripts/gen_secrets.py
```

**Keep `VOTE_ENCRYPTION_KEY` safe and never change it** while the database holds votes. If it changes, every stored ballot becomes unreadable.

Then create `~/adamawa/backend/.env` (with `nano .env`, or the Files tab):

```
FLASK_APP=wsgi:app
FLASK_ENV=production
TRUST_PROXY=true
ALLOW_DEMO_SEED=true

SECRET_KEY=...            # from gen_secrets.py
VOTE_ENCRYPTION_KEY=...   # from gen_secrets.py
IDENTIFIER_PEPPER=...     # from gen_secrets.py

DATABASE_URL=mysql+pymysql://USERNAME:MYSQL_PASSWORD@USERNAME.mysql.pythonanywhere-services.com/USERNAME$adamawa?charset=utf8mb4

TEST_ADMIN_PASSWORD=...   # for admin@example.com (10+ chars, letter + number)
TEST_VOTER_PASSWORD=...   # for voter1…voter5@example.com
```

## 4. Create the tables and the test accounts

```bash
cd ~/adamawa/backend
flask db upgrade
flask seed-test-users
```

This creates 21 LGAs, 1 admin (`admin@example.com`) and 5 verified voters (`voter1@example.com` … `voter5@example.com`), using the passwords from `.env`. Add `--voters 10` for up to 10 voters.

## 5. Create the web app

On the **Web** tab:

1. **Add a new web app → Manual configuration**, with the same Python version as the virtualenv.
2. **Virtualenv:** `/home/USERNAME/.virtualenvs/adamawa-venv`
3. **Source code:** `/home/USERNAME/adamawa/backend`
4. Open the **WSGI configuration file** link and replace its contents with:
   ```python
   import sys

   path = "/home/USERNAME/adamawa/backend"
   if path not in sys.path:
       sys.path.insert(0, path)

   from wsgi import app as application  # noqa: E402
   ```
5. **Static files:** URL `/static/`, directory `/home/USERNAME/adamawa/backend/app/static`
6. **Force HTTPS: Enabled.** This is required. Production uses HTTPS-only cookies, so sign-in fails on a plain `http://` page.
7. Click **Reload**, then open `https://USERNAME.pythonanywhere.com`.

## Updating after a `git push`

```bash
cd ~/adamawa && git pull
cd backend && pip install -r requirements.txt && flask db upgrade
```

Then click **Reload** on the Web tab.

## Resetting the database and test accounts

```bash
cd ~/adamawa/backend
flask reset-demo --yes
flask seed-test-users
```

This deletes **all** data (elections, votes, registered voters), then recreates the test accounts with the current passwords in `.env`.

## Troubleshooting sign-in

- **"Your session security token is missing or expired":** check that Force HTTPS is on and that you're using the `https://` address. Then see the error log (Web tab). With `security.csrf_rejected` entries the audit log records the exact reason.
- **"Invalid email or password":** the passwords were set when the accounts were created. Changing `.env` later does not change them; reset as above.
- **Errors after an update:** check the **error log** on the Web tab.

## Notes and limits

- **Free plan:** the web app must be extended from the Web tab every 3 months or it is disabled.
- **Rate limits** are kept in memory, per worker process, and reset on reload. That's fine for a demo.
- **Production settings** (`FLASK_ENV=production`): Secure HTTPS-only cookies and HSTS are switched on, the app trusts exactly one proxy hop (`TRUST_PROXY=true`, needed for HTTPS detection and correct client IPs in audit logs), logs are JSON, and the demo admin override is refused.
- `ALLOW_DEMO_SEED=true` is what lets the test accounts be created on a server. Default passwords are refused there; you must set your own.
