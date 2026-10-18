# Product Requirements Document (PRD)
## Adamawa State Local Government Online Voting Prototype

## 1. Product overview

Build a secure, web-based online voting prototype for simulated Adamawa State local government elections. The product must support the electoral hierarchy of Adamawa State—Local Government Areas (LGAs), wards, and polling units—and provide separate experiences for voters and authorized electoral administrators.

This is an academic proof of concept only. It must never be described or presented as an officially approved platform for a real public election. The implementation should make this limitation visible in the UI and documentation.

The existing project will be created manually first with a React frontend and Flask backend. After that, an AI coding agent will modify the existing project, implement the features below, run tests, and produce a working local prototype.

## 2. Product goals

- Enable a verified simulated voter to authenticate and cast one vote per election.
- Allow administrators to configure simulated elections, candidates, electoral locations, and voter verification.
- Protect credentials, sessions, vote payloads, and administrative actions using appropriate web-security controls.
- Enforce ballot secrecy within the limits of an academic prototype.
- Compute and display results only when the election is configured to publish them.
- Provide a simple, accessible workflow for users with limited computer literacy.
- Maintain clear audit records for administrative and security-sensitive actions.
- Make the codebase modular, testable, documented, and easy to extend.

## 3. Non-goals and safety boundary

- Do not integrate with official INEC, ADSIEC, NIMC, BVAS, or any government voter database.
- Do not use real voter personal data, real NINs, real credentials, or real election results.
- Do not claim legal compliance, election certification, end-to-end verifiability, coercion resistance, or production readiness.
- Do not implement biometric authentication in this version.
- Do not use blockchain as a substitute for election security.
- Do not expose decrypted individual ballots to administrators.
- Do not add functionality that enables a real election without explicit future security, legal, operational, and independent audit work.

## 4. Users and roles

### 4.1 Voter

A simulated eligible voter who can register or receive an account, complete verification, authenticate, view eligible elections and candidates, cast a ballot, and receive a non-revealing confirmation.

### 4.2 Electoral administrator

An authorized user who can manage simulated electoral data, verify voters, configure elections, manage candidates, monitor participation, publish results, and inspect audit events.

Use role-based access control. At minimum support `admin` and `voter` roles. Structure the authorization layer so additional roles such as `super_admin` or `auditor` can be added later.

## 5. Core assumptions

- The prototype covers the 21 LGAs of Adamawa State.
- The seed data may include illustrative LGA, ward, and polling-unit records, but must be clearly marked as demo data unless verified from an authoritative dataset.
- Each voter belongs to one LGA, one ward, and one polling unit.
- Candidates belong to an election and an LGA or electoral scope.
- The first release supports a simulated local government council election. The data model should allow additional election types later.
- The system uses a relational database and a three-tier architecture: React presentation, Flask application logic, and MySQL data storage.

## 6. Functional requirements

### 6.1 Public and landing experience

- Display the product name, purpose, demo-only warning, and links to voter login, registration, administrator login, and help.
- Clearly state that the application is a simulated academic prototype and not an official election platform.
- Provide accessible error, loading, and empty states.

### 6.2 Voter registration and verification

- Allow a user to submit the required simulated voter information: name, email, phone, voter identification number, LGA, ward, polling unit, and password.
- Validate all fields on the client and server.
- Normalize email, phone, and voter-ID input before checking uniqueness.
- Never store plaintext passwords.
- New accounts must remain unverified until an administrator verifies them, unless a clearly documented demo-seeding mode is used.
- Prevent duplicate email, phone, or voter-ID records.
- Provide registration status and safe next steps after submission.
- Do not log passwords, OTPs, raw voter IDs, or ballot choices.

### 6.3 Authentication and sessions

- Support voter and administrator login.
- Use secure password hashing with bcrypt or an equivalent adaptive password hash.
- Use secure, short-lived authentication sessions or access tokens with refresh handling implemented safely.
- Protect login and OTP endpoints with rate limiting.
- Add optional OTP support behind a feature flag. For local development, use a mock OTP provider and never display real secrets in production-like logs.
- Provide logout and session invalidation.
- Return generic authentication errors that do not reveal whether an account exists.
- Prevent access to protected routes without authentication.

### 6.4 Voter dashboard

- Show the voter’s verification status and electoral location using masked or minimal personal data.
- List active, upcoming, and completed elections relevant to the voter.
- Show whether the voter has already participated in each election without revealing the ballot choice.
- Disable voting outside the configured election period.

### 6.5 Ballot and candidate display

- Display the election title, instructions, opening and closing times, and a clear demo-election notice.
- Display only candidates eligible for the voter’s election scope.
- Show candidate name, party affiliation, photo placeholder if available, and manifesto summary.
- Use a clear single-choice ballot for the first release.
- Require an explicit review step before final submission.
- Do not preselect a candidate.
- Make the ballot usable with keyboard navigation and screen readers.

### 6.6 Vote casting and submission

- Verify the authenticated voter, election status, eligibility, and one-vote rule on the server immediately before submission.
- Require a final confirmation dialog that explains submission is irreversible in this prototype.
- Encrypt the ballot payload before persistence using a documented cryptographic approach and key-management strategy suitable for a prototype.
- Store only the minimum metadata needed for integrity, auditing, and result computation.
- Use a database-level unique constraint on `(election_id, voter_id)` as a second layer against duplicate voting.
- Make vote submission transactional and idempotent where possible.
- Return a confirmation receipt/reference that does not reveal the candidate selection.
- Never expose the plaintext ballot through APIs, logs, admin screens, analytics, or error messages.
- If a vote fails, clearly state that no vote was recorded unless the transaction committed successfully.

### 6.7 Administrator dashboard

- Provide summary cards for elections, verified voters, participation, and pending actions.
- Restrict all admin routes through server-side authorization.
- Support voter search and filtering by verification status and electoral location without exposing unnecessary personal information.
- Verify, reject, suspend, or reactivate simulated voter records, with a reason field where appropriate.
- Create, edit, schedule, open, close, archive, and cancel elections subject to safe state transitions.
- Configure election scope and applicable LGA.
- Create, edit, activate, deactivate, and remove candidates subject to election-state rules.
- Prevent destructive changes after voting begins unless an explicit, documented demo-admin override is used.
- View participation counts, never individual voter choices.
- Publish or hide aggregate results according to election configuration.
- Review a paginated, filterable audit log.

### 6.8 Results

- Compute results only from valid recorded votes.
- Display aggregate totals by candidate and percentage where appropriate.
- Provide table and simple chart views in the frontend.
- Do not show results before the configured publication time.
- Clearly label results as simulated.
- Ensure an administrator cannot infer a voter’s selection from a single-vote query or overly granular endpoint.
- Define and document tie handling for the prototype, such as displaying a tie and requiring administrative resolution outside the system.

### 6.9 Audit logging

Record security-sensitive and administrative actions, including:

- Successful and failed login attempts, subject to privacy minimization.
- Voter verification and status changes.
- Election and candidate changes.
- Election opening, closing, publication, and cancellation.
- Vote submission outcome without recording the ballot choice.
- Permission failures and rate-limit events where useful.

Audit records should include event type, actor ID where available, timestamp, request correlation ID, and a sanitized description. Minimize or hash IP information according to the prototype’s privacy policy. Audit logs must be append-oriented and inaccessible to ordinary voters.

## 7. Data model

Implement migrations and constraints for at least these entities:

- `users`: id, role, email, phone, password_hash, status, created_at, updated_at, last_login_at.
- `voters`: id, user_id, voter_id_hash or protected identifier, name fields, lga_id, ward_id, polling_unit_id, verification_status, verified_by, verified_at, created_at, updated_at.
- `admins`: either a role-backed user record or a dedicated profile linked to users.
- `local_government_areas`: id, name, code, active.
- `wards`: id, lga_id, name, code, active.
- `polling_units`: id, ward_id, name, code, active.
- `elections`: id, title, type, description, scope, start_at, end_at, status, results_published_at, created_by, created_at, updated_at.
- `candidates`: id, election_id, lga_id if applicable, full_name, party_affiliation, manifesto_summary, photo_url or placeholder, status, created_at, updated_at.
- `votes`: id, election_id, voter_id, encrypted_vote_payload, payload_nonce or IV, integrity_hash, receipt_reference, cast_at, created_at. Add a unique constraint on election and voter.
- `audit_logs`: id, actor_user_id, event_type, entity_type, entity_id, sanitized_description, request_id, ip_hash if used, created_at.
- `otp_challenges` if OTP is enabled: id, user_id, purpose, code_hash, expires_at, attempts, consumed_at, created_at.

Use foreign keys, indexes, check constraints where supported, timestamps, and explicit enum/state validation. Do not store a plaintext NIN or other sensitive identifier unless the prototype documentation explicitly justifies it; prefer a protected or hashed demo identifier.

## 8. API requirements

Build a versioned REST API under `/api/v1`. Return consistent JSON envelopes, validation errors, correlation IDs, and appropriate HTTP status codes.

Suggested endpoint groups:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/otp/request`
- `POST /auth/otp/verify`
- `GET /me`
- `GET /elections`
- `GET /elections/{id}`
- `GET /elections/{id}/ballot`
- `POST /elections/{id}/votes`
- `GET /elections/{id}/participation-status`
- `GET /elections/{id}/results`
- `GET /locations/lgas`
- `GET /locations/lgas/{id}/wards`
- `GET /locations/wards/{id}/polling-units`
- `GET /admin/dashboard`
- `GET /admin/voters`
- `PATCH /admin/voters/{id}/verification`
- `GET /admin/elections`
- `POST /admin/elections`
- `PATCH /admin/elections/{id}`
- `POST /admin/elections/{id}/open`
- `POST /admin/elections/{id}/close`
- `POST /admin/elections/{id}/publish-results`
- `GET /admin/elections/{id}/candidates`
- `POST /admin/elections/{id}/candidates`
- `PATCH /admin/candidates/{id}`
- `GET /admin/audit-logs`

The AI may adjust endpoint names, but it must preserve the same capabilities, authorization boundaries, and response semantics. Generate an OpenAPI document or equivalent API documentation.

## 9. Frontend requirements

Use React with TypeScript and a responsive component system. The frontend should include:

- Public landing page.
- Voter registration flow.
- Login and optional OTP flow.
- Voter dashboard.
- Election details and ballot page.
- Ballot review and confirmation modal.
- Vote confirmation receipt page.
- Results page with tables and charts.
- Admin dashboard.
- Voter verification management.
- Election management.
- Candidate management.
- Audit-log viewer.
- Shared loading, error, empty, confirmation, and unauthorized states.

Design principles:

- Plain language and clear instructions.
- Mobile-first responsive layout.
- Strong contrast and visible focus states.
- Keyboard accessibility.
- No dark patterns or confusing preselected choices.
- Never display ballot selections after submission.
- Use masking for sensitive identifiers.
- Keep demo-only and non-production warnings visible in relevant workflows.

## 10. Backend requirements

Use Flask with a modular application structure, for example:

- `app/__init__.py` for application factory.
- `app/config.py` for environment-based configuration.
- `app/extensions.py` for database, migration, CORS, limiter, and security extensions.
- `app/models/` for database models.
- `app/routes/` or `app/api/` for versioned blueprints.
- `app/services/` for authentication, voting, encryption, results, and audit services.
- `app/schemas/` for request and response validation.
- `app/security/` for authorization and security utilities.
- `tests/` for unit, integration, and API tests.

Use SQLAlchemy and migrations. Use parameterized queries through the ORM or safe query APIs. Keep business rules out of route handlers where practical. Add structured logging with secrets and ballot contents removed.

## 11. Security requirements

Treat security as a prototype requirement, not a claim of production election security.

- Hash passwords with bcrypt or an equivalent adaptive algorithm.
- Encrypt vote payloads at rest using a documented AES-256-GCM or equivalent authenticated-encryption design.
- Keep encryption keys outside source control and outside the database; load them from environment or a local secret-management mechanism.
- Use HTTPS in deployment documentation.
- Apply CSRF protection where cookie-based authentication is used.
- Configure secure, HttpOnly, SameSite cookies if sessions are cookie-based.
- Validate and sanitize all input.
- Use ORM-safe database access.
- Apply server-side authorization to every protected operation.
- Add login, OTP, and vote-submission rate limits.
- Prevent replay and duplicate submissions.
- Configure safe CORS for known frontend origins only.
- Avoid sensitive data in URLs, logs, analytics, exception messages, and client storage.
- Add security headers, including a suitable Content Security Policy in deployment guidance.
- Provide generic error messages to users and detailed but sanitized server logs.
- Add dependency pinning and a security-focused README section.
- Include a threat-model document covering impersonation, double voting, ballot secrecy, malware, server compromise, denial of service, insider misuse, coercion, and database compromise.

Explicit limitation: encryption of a database record alone does not provide full end-to-end verifiability or guaranteed ballot secrecy in a real election. The UI and documentation must state this.

## 12. Testing requirements

Implement automated tests before declaring the build complete.

### Unit tests

- Password hashing and verification.
- Input validation and normalization.
- Election state transitions.
- Eligibility checks.
- One-vote enforcement.
- Vote encryption and decryption round trip.
- Result aggregation.
- Authorization helpers.

### Integration/API tests

- Registration and duplicate detection.
- Login, logout, and session expiry.
- Admin-only endpoint protection.
- Voter verification flow.
- Ballot retrieval for eligible and ineligible voters.
- Successful vote submission.
- Duplicate vote rejection.
- Voting outside the election window.
- Results hidden before publication.
- Audit events created for sensitive actions.

### Security tests

- SQL injection-resistant input handling.
- CSRF protection if applicable.
- Rate limiting behavior.
- Broken access-control attempts.
- Session fixation or token misuse checks.
- Sensitive data absence from responses and logs.
- Malformed payload handling.

### Frontend tests

- Registration validation.
- Login and protected-route behavior.
- Candidate selection and review flow.
- Confirmation modal behavior.
- Results rendering.
- Admin permission-based navigation.

### Acceptance test set

Seed at least 20 simulated voters distributed across multiple LGAs and wards, several candidates, and at least one demo election. Test the full workflow from registration or seeded account through voting and result publication. Include negative cases for duplicate voting, unauthorized admin access, incomplete forms, malformed input, and voting outside the election window.

## 13. Seed data and demo mode

Provide a safe local seed command that creates:

- All 21 Adamawa State LGA names only if the dataset is validated; otherwise use clearly labeled demo locations.
- Demo wards and polling units.
- Demo administrator credentials printed once to the terminal or documented through environment variables, never hardcoded into production code.
- At least 20 demo voters.
- A demo election with candidates and a controllable schedule.

Include a reset command that is clearly marked destructive and works only in a local development environment.

## 14. Environment and commands

Create `.env.example` files for frontend and backend configuration. Include database URL, Flask environment, secret keys, JWT/session settings, CORS origins, encryption key location, rate-limit settings, and demo-mode flags. Never commit `.env` files.

The final README must document commands for:

- Installing frontend and backend dependencies.
- Starting MySQL.
- Creating the database.
- Running migrations.
- Seeding demo data.
- Starting the Flask API.
- Starting the React app.
- Running all tests.
- Running linting and formatting.
- Resetting local demo data.

## 15. Definition of done

The implementation is complete when:

- The manually created frontend and backend projects run locally.
- A voter can complete the simulated registration/verification/login flow.
- An eligible voter can view a ballot and submit exactly one vote.
- A duplicate or unauthorized vote is rejected safely.
- An administrator can manage voters, elections, candidates, and result publication.
- Aggregate results are computed and displayed only when allowed.
- Sensitive operations create sanitized audit records.
- Database migrations, seed data, API documentation, and environment examples are included.
- Automated tests cover the main happy paths and security-sensitive negative paths.
- The README explains the prototype’s limitations and explicitly states that it is not approved for real elections.
- No secrets, real voter data, plaintext passwords, plaintext ballot choices, or unsupported government integrations are included.

## 16. AI coding-agent instructions

You are modifying an existing project, not creating a new project from scratch. First inspect the repository, current package files, environment files, and existing routes/components. Preserve working code where possible and avoid unnecessary rewrites.

Work in small, verifiable increments:

1. Inspect and summarize the current project structure.
2. Set up configuration, database connectivity, migrations, and shared error handling.
3. Implement authentication and role-based authorization.
4. Implement location, voter, election, and candidate models and admin workflows.
5. Implement the secure vote-submission transaction and one-vote constraint.
6. Implement results, audit logs, seed data, and reset tooling.
7. Implement frontend routes and user workflows.
8. Add tests, documentation, and security checks.
9. Run the application and tests, fix failures, and report exact commands and remaining limitations.

Do not silently weaken security to make a test pass. If a requirement conflicts with a safe implementation, explain the conflict, choose the safer behavior, and document it. Do not claim the system is production-ready or suitable for a real public election.
