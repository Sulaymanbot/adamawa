"""Authentication endpoints."""

from flask import g
from flask_wtf.csrf import generate_csrf

from app.api import api_v1, rate
from app.errors import ok
from app.extensions import limiter
from app.schemas import LoginRequest, OtpVerifyRequest, RegisterRequest, parse_body
from app.services import auth_service


def _fresh_csrf() -> str:
    g.pop("csrf_token", None)
    return generate_csrf()


def _landing_for(role: str) -> str:
    return "/admin" if role in {"admin", "super_admin", "auditor"} else "/dashboard"


@api_v1.get("/auth/csrf")
def csrf_token():
    return ok({"csrf_token": generate_csrf()})


@api_v1.post("/auth/register")
@limiter.limit(rate("REGISTER_RATE_LIMIT"))
def register():
    data = parse_body(RegisterRequest)
    voter = auth_service.register_voter(data)
    return ok(
        {
            "voter_id": voter.id,
            "verification_status": voter.verification_status,
            "next_steps": "An officer will verify your account. Sign in anytime to check your status.",
        },
        201,
    )


@api_v1.post("/auth/login")
@limiter.limit(rate("LOGIN_RATE_LIMIT"))
def login():
    data = parse_body(LoginRequest)
    result = auth_service.login(data.email, data.password)
    result["csrf_token"] = _fresh_csrf()
    if not result["otp_required"]:
        result["redirect"] = _landing_for(result["user"]["role"])
    return ok(result)


@api_v1.post("/auth/otp/request")
@limiter.limit(rate("OTP_RATE_LIMIT"))
def otp_request():
    auth_service.resend_otp()
    return ok({"sent": True, "message": "A new code has been sent."})


@api_v1.post("/auth/otp/verify")
@limiter.limit(rate("OTP_RATE_LIMIT"))
def otp_verify():
    data = parse_body(OtpVerifyRequest)
    result = auth_service.verify_otp(data.code)
    result["csrf_token"] = _fresh_csrf()
    result["redirect"] = _landing_for(result["user"]["role"])
    return ok(result)


@api_v1.post("/auth/logout")
def logout():
    auth_service.logout()
    return ok({"logged_out": True, "csrf_token": _fresh_csrf()})
