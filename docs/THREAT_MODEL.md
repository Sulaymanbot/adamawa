# Threat Model — Adamawa LG Online Voting (Simulated Prototype)

Scope: the Flask application, its MySQL database, the browser UI and the operators of a **local, simulated** deployment. This document explains what the prototype does and does not defend against. It is not a certification and the system is **not suitable for a real public election**.

## Assets

| Asset | Why it matters |
|---|---|
| Ballot contents | Ballot secrecy and result integrity |
| One-vote-per-voter guarantee | Prevents double voting |
| Voter identity data (names, contacts, voter IDs) | Privacy |
| Credentials and sessions | Impersonation |
| `VOTE_ENCRYPTION_KEY`, `SECRET_KEY`, `IDENTIFIER_PEPPER` | Compromising these breaks secrecy, sessions and identifier privacy |
| Election configuration and published results | Integrity and public trust |
| Audit log | Accountability |

## Actors

Honest voter · malicious voter · external attacker · malicious or careless administrator (insider) · database/server operator · malware on a voter device · coercer.

## Threats and mitigations

| # | Threat | Prototype mitigations | Residual risk / not covered |
|---|---|---|---|
| 1 | **Impersonation** (credential stuffing, guessing, session theft) | bcrypt; generic login errors with timing equalisation; login rate limit (10/min/IP); optional OTP second factor (hashed, expiring, attempt-limited); HttpOnly + SameSite cookies; server-side sessions rotated at login (no fixation), revocable, idle/absolute expiry; CSRF tokens; voters must be verified by an officer | Mock OTP only (no real SMS/email); no device binding; a phished password + OTP still works; per-IP limits are bypassable from many IPs |
| 2 | **Double voting** | Transaction locks the voter row (`SELECT … FOR UPDATE`) and re-checks for an existing ballot; `UNIQUE(election_id, voter_id)` DB constraint as second layer; idempotency key returns the original receipt for retries; duplicate attempts are audited | Duplicate *identities* (one person registering twice with different demo IDs) are only caught by officer verification |
| 3 | **Ballot secrecy** | AES-256-GCM per ballot with fixed-length padding; key held outside DB/repo; no endpoint/log/admin view exposes a choice; decryption only in the results service, only in aggregate, only after close + publish; small races (< 3 votes) withheld; no per-ward/polling-unit breakdown; choice never stored client-side | **The `votes` row links voter → ciphertext** (needed for one-vote enforcement). Anyone with DB + key can link ballots to voters. Real systems separate identity from ballot (e.g., Estonia's double envelope, mix-nets, homomorphic tallying, blind signatures). Timestamps in `votes` and `audit_logs` could aid correlation. |
| 4 | **Malware on the voter's device** | CSP `'self'`, no inline script, no third-party runtime assets; review + confirmation step; receipt check | Not addressed. A compromised browser can change or read the selection before submission. No cast-as-intended verification. |
| 5 | **Server compromise** | Secrets in environment; least-privilege DB user; ORM-only queries; security headers; dependency pinning; audit log | An attacker with the server and key can read or alter ballots and logs. No HSM/threshold key sharing, no external log anchoring, no reproducible builds. |
| 6 | **Denial of service** | Rate limits on login/OTP/vote/registration; 64 KB request limit; pagination caps | No WAF, CDN or autoscaling. In-memory limiter is per process. A real election needs DDoS protection and a capacity plan. |
| 7 | **Insider misuse (administrator)** | RBAC permission map; admins cannot vote; masked PII in admin views; elections and candidates lock after voting starts (demo override is audited and restricted); results only after close; every admin action audited with request ID; audit log append-only at ORM level | A DB administrator can bypass the ORM and edit tables directly. No two-person rule for close/publish. Audit log is not cryptographically chained. |
| 8 | **Coercion / vote buying** | Receipts do not reveal the choice; the UI never re-displays a submitted choice | Remote unsupervised voting is inherently coercible. No re-voting / last-vote-counts mechanism (votes are final by design here). |
| 9 | **Database compromise (theft of a dump)** | Ballots encrypted (key not in DB); passwords bcrypt-hashed; voter IDs HMAC-hashed with a pepper not in DB; OTP codes hashed; session tokens stored as SHA-256 | Names, emails and phones are stored in plaintext (masked only in the UI). With the dump **and** the env secrets everything is exposed. |
| 10 | **Injection / XSS / CSRF** | Pydantic validation with forbidden extra fields and strict types; ORM parameterisation; escaped LIKE wildcards; Jinja autoescape; JS inserts data via `textContent` only; CSP; CSRF tokens; open-redirect guard on `next` | — |
| 11 | **Tampering with stored ballots** | GCM authentication + associated data (election, receipt) + integrity hash; tampered rows counted as invalid and audited | Deleting a ballot row is not detectable from the ballot table alone (only the audit log and receipt checks would show it). |
| 12 | **Information leakage via logs/URLs** | No request bodies logged; sensitive log fields redacted; PII searches via POST body; generic 500 errors with request ID | Reverse-proxy logs must also be configured not to log bodies. |

## Explicit limitation

Encrypting database records **does not** provide end-to-end verifiability (cast-as-intended, recorded-as-cast, counted-as-recorded) or guaranteed ballot secrecy. The receipt check shows only that *a* ballot with that reference exists. It does not prove the ballot's content or that it was counted. A production-grade system would need independent cryptographic review, a verifiable voting protocol, legal backing, operational procedures, and independent penetration testing and audit.
