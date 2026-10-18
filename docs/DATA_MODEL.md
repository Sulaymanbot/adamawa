# Data Model

Implemented in `backend/app/models/` and `backend/migrations/versions/`. This document maps the tables to the Entity Relationship Diagram in Chapter 3 (§3.8.2) of the project report.

## Mapping to the Chapter 3 ERD

| Chapter 3 entity / attribute | Implemented as | Notes |
|---|---|---|
| **Voter** | `users` (login) + `voters` (profile) | Login is shared with administrators through `users` (PRD §7) |
| voter_id (PK) | `voters.id` | |
| surname, first_name, other_names | `voters.surname`, `first_name`, `other_names` | |
| email, phone | `users.email`, `users.phone` | Normalised (lower-case email, E.164 phone), unique |
| password_hash | `users.password_hash` | bcrypt |
| lga_id, ward_id, polling_unit_id (FK) | `voters.lga_id`, `ward_id`, `polling_unit_id` | Hierarchy validated on registration |
| nin | *not stored* | Replaced by `voters.voter_id_hash` (HMAC of a **demo** voter ID) + `voter_id_last4`. See DECISIONS #7 |
| registration_date | `voters.created_at` | |
| is_verified | `voters.verification_status` | `pending` / `verified` / `rejected` / `suspended`, plus `verified_by`, `verified_at`, `verification_reason` |
| **Administrator** | `users` (role `admin`) + `admins` | |
| admin_id (PK) | `admins.id` (`users.id` is the actor id in audit logs) | |
| full_name | `admins.full_name` | |
| email, password_hash, created_at | `users.email`, `users.password_hash`, `users.created_at` | |
| role | `users.role` | `voter`, `admin`, `super_admin`, `auditor` |
| status | `users.status` | `active`, `suspended`, `disabled` |
| **LocalGovernmentArea** (lga_id, lga_name, lga_code) | `local_government_areas` (id, name, code, active) | 21 LGAs seeded |
| **Ward** (ward_id, ward_name, lga_id) | `wards` (id, lga_id, name, code, active) | Unique (lga_id, code). Demo data |
| **PollingUnit** (polling_unit_id, polling_unit_name, polling_unit_code, ward_id) | `polling_units` (id, ward_id, name, code, active) | Unique (ward_id, code). Demo data |
| **Election** (election_id, election_title, election_type, start_date, end_date, status, created_by) | `elections` (id, title, type, description, scope, lga_id, start_at, end_at, status, results_published_at, created_by, created_at, updated_at) | CHECK constraints on type, scope, status and `end_at > start_at`. `scope`/`lga_id` consistency is also checked |
| **Candidate** (candidate_id, election_id, lga_id, full_name, party_affiliation, manifesto_summary) | `candidates` (+ photo_url, status, timestamps) | `status` active/inactive |
| **Vote** (vote_id, election_id, voter_id, encrypted_vote_payload, timestamp, verification_hash) | `votes` (id, election_id, voter_id, encrypted_vote_payload, payload_nonce, integrity_hash, receipt_reference, idempotency_key_hash, key_version, cast_at, created_at) | `verification_hash` → `integrity_hash`. **UNIQUE (election_id, voter_id)** prevents double voting. Unique `receipt_reference`. No plaintext choice column |
| **AuditLog** (log_id, admin_id, action, description, timestamp, IP_address) | `audit_logs` (id, actor_user_id, event_type, entity_type, entity_id, sanitized_description, request_id, ip_hash, created_at) | `admin_id` → `actor_user_id` (any actor, including voters and anonymous). `IP_address` → keyed `ip_hash`. Append-only at the ORM level |
| — | `otp_challenges` (id, user_id, purpose, code_hash, expires_at, attempts, consumed_at, created_at) | Optional second factor |
| — | `user_sessions` (id, token_hash, user_id, created_at, last_seen_at, expires_at, revoked_at) | Server-side, revocable sessions |

## Relationships

- One LGA has many wards. One ward has many polling units.
- Each voter belongs to exactly one LGA, ward and polling unit.
- One user has at most one voter profile or admin profile.
- One election has many candidates. Each candidate belongs to one LGA (the race they contest).
- One voter casts at most one vote per election (DB constraint).
- One user (actor) has many audit log entries.

## Ballot payload (inside the ciphertext)

```json
{"v": 1, "e": <election_id>, "c": <candidate_id>, "l": <lga_id>}
```

The payload is padded with spaces to 96 bytes before AES-256-GCM encryption. Associated data is `adv:v1:election=<id>:receipt=<receipt_reference>`. The `integrity_hash` is SHA-256(aad | nonce | ciphertext).
