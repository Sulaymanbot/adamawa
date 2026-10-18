"""OpenAPI 3.1 document, built from the route table and pydantic schemas."""

from __future__ import annotations

from flask import jsonify

from app import schemas
from app.api import api_v1

# (method, path, summary, auth, request schema, tag)
ENDPOINTS = [
    ("get", "/auth/csrf", "Get a CSRF token for state-changing requests", "public", None, "Auth"),
    ("post", "/auth/register", "Register a simulated voter (starts as pending)", "public", "RegisterRequest", "Auth"),
    ("post", "/auth/login", "Sign in (may require an OTP step)", "public", "LoginRequest", "Auth"),
    ("post", "/auth/logout", "Sign out and revoke the server-side session", "any", None, "Auth"),
    ("post", "/auth/otp/request", "Re-send the one-time code for a pending sign-in", "otp-pending", None, "Auth"),
    ("post", "/auth/otp/verify", "Complete sign-in with the one-time code", "otp-pending", "OtpVerifyRequest", "Auth"),
    ("get", "/me", "Current user profile (masked)", "any", None, "Voter"),
    ("get", "/locations/lgas", "List LGAs", "public", None, "Locations"),
    ("get", "/locations/lgas/{lga_id}/wards", "List wards in an LGA", "public", None, "Locations"),
    ("get", "/locations/wards/{ward_id}/polling-units", "List polling units in a ward", "public", None, "Locations"),
    ("get", "/elections", "Elections relevant to the signed-in voter", "voter", None, "Voter"),
    ("get", "/elections/{election_id}", "Election details", "voter", None, "Voter"),
    ("get", "/elections/{election_id}/ballot", "Ballot (candidates for the voter's LGA)", "voter", None, "Voter"),
    ("post", "/elections/{election_id}/votes", "Cast a vote (send Idempotency-Key header)", "voter", "VoteRequest", "Voter"),
    ("get", "/elections/{election_id}/participation-status", "Has the voter voted? (never the choice)", "voter", None, "Voter"),
    ("get", "/elections/{election_id}/results", "Aggregate results, only once published", "public", None, "Results"),
    ("get", "/results", "Elections with published results", "public", None, "Results"),
    ("post", "/receipts/verify", "Check that a receipt exists in the ballot box", "public", "ReceiptCheckRequest", "Results"),
    ("get", "/admin/dashboard", "Summary statistics", "admin", None, "Admin"),
    ("get", "/admin/voters", "List voters by filter (status, lga_id, ward_id, page)", "admin", None, "Admin"),
    (
        "post",
        "/admin/voters/search",
        "Text search (name, exact email, exact voter ID) in the request body",
        "admin",
        "VoterSearchRequest",
        "Admin",
    ),
    (
        "patch",
        "/admin/voters/{voter_id}/verification",
        "Verify / reject / suspend / reactivate a voter",
        "admin",
        "VerificationRequest",
        "Admin",
    ),
    ("get", "/admin/elections", "List elections with participation", "admin", None, "Admin"),
    ("post", "/admin/elections", "Create an election (draft)", "admin", "ElectionCreate", "Admin"),
    ("get", "/admin/elections/{election_id}", "Election details for admins", "admin", None, "Admin"),
    ("patch", "/admin/elections/{election_id}", "Edit an election (draft/scheduled only)", "admin", "ElectionUpdate", "Admin"),
    ("post", "/admin/elections/{election_id}/schedule", "draft -> scheduled", "admin", "ElectionAction", "Admin"),
    ("post", "/admin/elections/{election_id}/unschedule", "scheduled -> draft", "admin", "ElectionAction", "Admin"),
    ("post", "/admin/elections/{election_id}/open", "Open voting", "admin", "ElectionAction", "Admin"),
    ("post", "/admin/elections/{election_id}/close", "Close voting", "admin", "ElectionAction", "Admin"),
    ("post", "/admin/elections/{election_id}/archive", "Archive a closed/cancelled election", "admin", "ElectionAction", "Admin"),
    ("post", "/admin/elections/{election_id}/cancel", "Cancel (reason required if open)", "admin", "ElectionAction", "Admin"),
    (
        "post",
        "/admin/elections/{election_id}/publish-results",
        "Publish (optionally at a time) or hide results",
        "admin",
        "PublishRequest",
        "Admin",
    ),
    ("get", "/admin/elections/{election_id}/candidates", "List candidates", "admin", None, "Admin"),
    ("post", "/admin/elections/{election_id}/candidates", "Add a candidate", "admin", "CandidateCreate", "Admin"),
    (
        "patch",
        "/admin/candidates/{candidate_id}",
        "Edit / activate / deactivate a candidate",
        "admin",
        "CandidateUpdate",
        "Admin",
    ),
    ("delete", "/admin/candidates/{candidate_id}", "Remove a candidate (before voting only)", "admin", None, "Admin"),
    ("get", "/admin/audit-logs", "Audit log (event_type, actor_user_id, entity_type, from, to, page)", "admin", None, "Admin"),
]

ENVELOPE = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "data": {},
        "meta": {"type": "object"},
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "details": {"type": "array", "items": {"type": "object"}},
            },
        },
        "request_id": {"type": "string"},
    },
}


def build_spec() -> dict:
    components: dict = {"Envelope": ENVELOPE}
    paths: dict = {}
    for method, path, summary, auth, body, tag in ENDPOINTS:
        op: dict = {
            "summary": summary,
            "tags": [tag],
            "x-auth": auth,
            "responses": {
                "200": {
                    "description": "Success",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Envelope"}}},
                },
                "4XX": {"description": "Error envelope"},
            },
        }
        params = [seg[1:-1] for seg in path.split("/") if seg.startswith("{")]
        if params:
            op["parameters"] = [{"name": p, "in": "path", "required": True, "schema": {"type": "integer"}} for p in params]
        if method in {"post", "patch", "delete"}:
            op.setdefault("parameters", []).append(
                {"name": "X-CSRFToken", "in": "header", "required": True, "schema": {"type": "string"}}
            )
        if body:
            model = getattr(schemas, body)
            schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
            for name, sub in schema.pop("$defs", {}).items():
                components[name] = sub
            components[body] = schema
            op["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{body}"}}},
            }
        if auth != "public":
            op["security"] = [{"sessionCookie": []}]
        paths.setdefault(f"/api/v1{path}", {})[method] = op
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Adamawa LG Online Voting – Simulated Prototype API",
            "version": "1.0.0",
            "description": "Academic prototype. NOT an official election platform. All responses use the Envelope shape.",
        },
        "paths": paths,
        "components": {
            "schemas": components,
            "securitySchemes": {"sessionCookie": {"type": "apiKey", "in": "cookie", "name": "adv_session"}},
        },
    }


@api_v1.get("/openapi.json")
def openapi():
    return jsonify(build_spec())
